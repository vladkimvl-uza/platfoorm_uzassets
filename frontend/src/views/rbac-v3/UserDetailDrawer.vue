<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue';
import { rbacV3Api, deriveAccessMap, rolesApi, groupsApi, adminMfaApi, generatePassword, levelsToPermissions } from '@/api/rbacV3';
import { MODULE_REGISTRY, type AccessLevel } from '@/composables/usePermissions';
import type { RbacV3UserDetail, RbacV3UserBrief, RbacV3Role, RbacV3Group, AdminMfaRow } from '@/api/rbacV3';
import { moderationApi } from '@/api/moderation';
import { companiesApi, type SectorBrief } from '@/api/companies';
import { auditApi, actionMeta, type AuditEventRead, type AuditEventDetail } from '@/api/audit';
import UserAvatar from '@/components/rbac-v3/UserAvatar.vue';
import RoleChip from '@/components/rbac-v3/RoleChip.vue';
import RoleAssignmentPicker from '@/components/rbac-v3/RoleAssignmentPicker.vue';
import ModuleSelectGrid from '@/components/rbac-v3/ModuleSelectGrid.vue';
import InviteUserModal from '@/components/rbac-v3/InviteUserModal.vue';
import { createPreviewToken } from '@/api/rbacV3';
import { useAuthStore } from '@/stores/auth';
import { useFormatters } from '@/composables/useFormatters';
import { presenceStatus, presenceLabel } from '@/composables/usePresence';
import { useToast } from '@/composables/useToast';
import { useI18n } from '@/composables/useI18n';
import { useConfirm } from '@/composables/useConfirm';
import { INTL_LOCALE } from '@/locale';

const toast = useToast();
const { t, locale } = useI18n();
const { confirmDialog, promptDialog } = useConfirm();

const fmt = useFormatters();

const auth = useAuthStore();
const canManage = computed(() =>
  auth.isOwner || auth.hasPermission('admin.users'),
);

// Presence-статус для шапки дровера.
const headStatus = computed(() => presenceStatus(detail.value?.last_seen_at));
// Аккаунт заблокирован lockout-ом по неудачным попыткам входа (locked_until в будущем).
const isLocked = computed(() => {
  const lu = detail.value?.locked_until;
  return !!lu && new Date(lu).getTime() > Date.now();
});

const props = defineProps<{ user: RbacV3UserBrief | null }>();
const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'changed'): void;
  (e: 'open-user', id: string): void;
}>();

type Tab = 'access' | 'profile' | 'activity' | 'security';
const tab = ref<Tab>('access');
const detail = ref<RbacV3UserDetail | null>(null);
const loading = ref(false);
const error = ref<string | null>(null);

watch(() => props.user?.id, async (newId) => {
  detail.value = null;
  if (!newId) return;
  loading.value = true;
  error.value = null;
  try {
    detail.value = await rbacV3Api.getUser(newId);
  } catch (e: any) {
    error.value = e?.response?.data?.detail || t('Не удалось загрузить данные');
  } finally {
    loading.value = false;
  }
}, { immediate: true });

const access = computed(() => deriveAccessMap(detail.value));
const accessCount = computed(() => {
  return Object.values(access.value.levels).filter(l => l !== 'none').length;
});
const lastLoginRelative = computed(() => {
  const dt = detail.value?.last_login_at;
  if (!dt) return '—';
  return fmt.fmtRelativeTime(dt);
});

// ─── Module access editor (прямые per-user гранты, OWNER/ADMIN) ──
const editingAccess = ref(false);
const draftLevels = ref<Record<string, AccessLevel>>({});
const savingAccess = ref(false);

function openAccessEditor() {
  draftLevels.value = { ...access.value.levels };
  editingAccess.value = true;
}
function cancelAccessEditor() {
  editingAccess.value = false;
}
async function saveAccess() {
  if (!detail.value) return;
  savingAccess.value = true;
  try {
    detail.value = await rbacV3Api.setPermissions(
      detail.value.id, levelsToPermissions(draftLevels.value),
    );
    editingAccess.value = false;
    // Явный фидбэк: сохранение прав — не то место, где можно молчать.
    toast.success(t('Доступ к модулям сохранён'));
    emit('changed');
  } catch (e: any) {
    const msg = e?.response?.data?.detail || t('Не удалось сохранить доступ к модулям');
    error.value = msg;
    toast.error(msg);
  } finally {
    savingAccess.value = false;
  }
}
// сбрасываем редактор при смене пользователя
watch(() => detail.value?.id, () => { editingAccess.value = false; });

// ─── Roles + groups catalog (loaded once for the pickers) ────────
const allRoles = ref<RbacV3Role[]>([]);
const allGroups = ref<RbacV3Group[]>([]);
const roleByCode = computed<Record<string, RbacV3Role>>(() => {
  const result: Record<string, RbacV3Role> = {};
  for (const role of allRoles.value) result[role.code] = role;
  return result;
});

function roleLabel(code: string): string {
  const roleIndex = detail.value?.role_codes.indexOf(code) ?? -1;
  return roleByCode.value[code]?.name_ru
    || (roleIndex >= 0 ? detail.value?.role_names[roleIndex] : undefined)
    || code;
}

async function loadCatalogs() {
  if (!canManage.value) return;
  try {
    if (!allRoles.value.length)  allRoles.value  = await rolesApi.list();
    if (!allGroups.value.length) allGroups.value = await groupsApi.list();
  } catch (e) {
    console.warn('[UserDetailDrawer] catalog load failed', e);
  }
}
onMounted(loadCatalogs);
watch(canManage, (v) => { if (v) loadCatalogs(); });

// ─── Sectors catalog (для отображения области доступа «По секторам») ──
const allSectors = ref<SectorBrief[]>([]);
const sectorMap = computed<Record<string, SectorBrief>>(() => {
  const m: Record<string, SectorBrief> = {};
  for (const s of allSectors.value) m[s.code] = s;
  return m;
});
function sectorLabel(code: string): string { return sectorMap.value[code]?.name_ru || code; }
function sectorColor(code: string): string { return sectorMap.value[code]?.color_hex || '#7F77DD'; }
// ─── Редактирование области доступа «По секторам» ─────────────────
// Блок был только для чтения: администратор видел выданные секторы, но не мог
// их изменить — приходилось пересоздавать пользователя. Бэкенд приём умеет
// (UserUpdatePayload.allowed_sectors) и проверяет потолок области актора.
const editingScope = ref(false);
const savingScope = ref(false);
const draftSectors = ref<string[]>([]);

function openScopeEditor(): void {
  draftSectors.value = [...(detail.value?.allowed_sectors || [])];
  editingScope.value = true;
}
function toggleSector(code: string): void {
  const i = draftSectors.value.indexOf(code);
  if (i >= 0) draftSectors.value.splice(i, 1);
  else draftSectors.value.push(code);
}
async function saveScope(): Promise<void> {
  if (!detail.value) return;
  savingScope.value = true;
  try {
    // Пустой список шлём как [] — бэкенд трактует его как «секторов нет»
    // (new_sectors = payload.allowed_sectors or None), то есть снятие области.
    detail.value = await rbacV3Api.update(detail.value.id, {
      allowed_sectors: draftSectors.value,
    });
    editingScope.value = false;
    emit('changed');
  } catch (e: any) {
    error.value = e?.response?.data?.detail || t('Не удалось сохранить область доступа');
  } finally {
    savingScope.value = false;
  }
}

const hasDataScope = computed(() =>
  !!(detail.value?.allowed_sectors?.length || detail.value?.allowed_companies?.length));
const allCompanies = ref<{ id: string; name: string }[]>([]);
onMounted(async () => {
  try { allSectors.value = await companiesApi.listSectors(); } catch { /* best-effort */ }
  try {
    const r = await companiesApi.list({ per_page: 500 } as any);
    const items = (r as any)?.items || (r as any)?.companies || (Array.isArray(r) ? r : []);
    allCompanies.value = (items || []).map((c: any) => ({ id: c.id, name: c.name_ru || c.name || c.code }))
      .filter((c: any) => c.id)
      .sort((a: any, b: any) => a.name.localeCompare(b.name, INTL_LOCALE[locale.value]));
  } catch { /* best-effort */ }
});

// ─── Admin-редактирование профиля (ФИО/отдел/должность/компания) ──
const editingProfile = ref(false);
const savingProfile = ref(false);
const profForm = ref({ full_name: '', department: '', job_title: '', organization_id: '' });
function openProfileEditor() {
  if (!detail.value) return;
  profForm.value = {
    full_name: detail.value.full_name || '',
    department: detail.value.department || '',
    job_title: detail.value.job_title || '',
    organization_id: detail.value.organization_id || '',
  };
  editingProfile.value = true;
}
async function saveProfile() {
  if (!detail.value) return;
  savingProfile.value = true;
  try {
    detail.value = await rbacV3Api.update(detail.value.id, {
      full_name: profForm.value.full_name.trim() || undefined,
      department: profForm.value.department.trim() || undefined,
      job_title: profForm.value.job_title.trim() || undefined,
      organization_id: profForm.value.organization_id || undefined,
    });
    editingProfile.value = false;
    emit('changed');
  } finally {
    savingProfile.value = false;
  }
}
// Смена пользователя → закрываем редактор профиля и чистим форму, иначе
// открытая форма показывает данные предыдущего юзера поверх нового (баг).
watch(() => detail.value?.id, () => {
  editingProfile.value = false;
  profForm.value = { full_name: '', department: '', job_title: '', organization_id: '' };
});
function companyName(id: string | null): string {
  if (!id) return '—';
  return allCompanies.value.find((c) => c.id === id)?.name || '—';
}

// ─── Roles editor state ──────────────────────────────────────────
const editingRoles = ref(false);
const draftRoleCodes = ref<string[]>([]);
const savingRoles = ref(false);

function openRoleEditor() {
  if (!detail.value) return;
  draftRoleCodes.value = [...detail.value.role_codes];
  editingRoles.value = true;
}

async function saveRoles() {
  if (!detail.value) return;
  savingRoles.value = true;
  try {
    detail.value = await rbacV3Api.update(detail.value.id, {
      role_codes: draftRoleCodes.value,
    });
    editingRoles.value = false;
    emit('changed');
  } catch (e: any) {
    error.value = e?.response?.data?.detail || t('Не удалось сохранить роли');
  } finally {
    savingRoles.value = false;
  }
}

// ─── Group memberships editor state ──────────────────────────────
const showAddMembership = ref(false);
const draftAddGroupId   = ref<string>('');
const draftAddRoleCode  = ref<string>('viewer');
const savingMembership  = ref(false);

const availableGroupsForAdd = computed(() => {
  if (!detail.value) return allGroups.value;
  const taken = new Set(detail.value.group_memberships.map(m => m.group_id));
  return allGroups.value.filter(g => !taken.has(g.id));
});

async function addMembership() {
  if (!detail.value || !draftAddGroupId.value) return;
  savingMembership.value = true;
  try {
    detail.value = await rbacV3Api.upsertMembership(
      detail.value.id, draftAddGroupId.value, draftAddRoleCode.value,
    );
    showAddMembership.value = false;
    draftAddGroupId.value = '';
    draftAddRoleCode.value = 'viewer';
    emit('changed');
  } catch (e: any) {
    error.value = e?.response?.data?.detail || t('Не удалось добавить членство');
  } finally {
    savingMembership.value = false;
  }
}

async function changeMembershipRole(groupId: string, newCode: string) {
  if (!detail.value) return;
  try {
    detail.value = await rbacV3Api.upsertMembership(
      detail.value.id, groupId, newCode,
    );
    emit('changed');
  } catch (e: any) {
    error.value = e?.response?.data?.detail || t('Не удалось сменить роль');
  }
}

async function removeMembership(groupId: string, groupName: string) {
  if (!detail.value) return;
  if (!(await confirmDialog({
    message: t('Убрать пользователя из группы «{group}»?', { group: groupName }),
    danger: true,
  }))) return;
  try {
    await rbacV3Api.removeMembership(detail.value.id, groupId);
    detail.value = await rbacV3Api.getUser(detail.value.id);
    emit('changed');
  } catch (e: any) {
    error.value = e?.response?.data?.detail || t('Не удалось убрать членство');
  }
}

// ─── Security tab: MFA status + password reset ────────────────────
const mfaRow = ref<AdminMfaRow | null>(null);
const mfaLoading = ref(false);

async function loadMfaStatus() {
  if (!canManage.value || !detail.value) return;
  mfaLoading.value = true;
  try {
    const ov = await adminMfaApi.overview();
    mfaRow.value = ov.users.find(u => u.id === detail.value!.id) || null;
  } catch (e) {
    console.warn('[UserDetailDrawer] mfa overview failed', e);
  } finally {
    mfaLoading.value = false;
  }
}

// Refresh MFA when the user changes or when the Security tab is opened.
watch(() => detail.value?.id, () => { mfaRow.value = null; });
watch(tab, (v) => { if (v === 'security') loadMfaStatus(); });

// ─── Activity tab: аудит-история действий пользователя ───────────
const activityEvents = ref<AuditEventRead[]>([]);
const activityLoading = ref(false);
const activityLoaded = ref(false);
const activityDenied = ref(false);

async function loadActivity() {
  if (!detail.value || activityLoading.value || activityLoaded.value) return;
  activityLoading.value = true;
  activityDenied.value = false;
  try {
    const res = await auditApi.listEvents({ actor_email: detail.value.email, per_page: 60 });
    activityEvents.value = res.items || [];
    activityLoaded.value = true;
  } catch (e: any) {
    if (e?.response?.status === 403) activityDenied.value = true;
    else error.value = e?.response?.data?.detail || t('Не удалось загрузить активность');
  } finally {
    activityLoading.value = false;
  }
}
// сбрасываем при смене пользователя; грузим при открытии вкладки
watch(() => detail.value?.id, () => {
  activityEvents.value = []; activityLoaded.value = false; activityDenied.value = false;
  expandedId.value = null; detailCache.value = {};
});
watch(tab, (v) => { if (v === 'activity') loadActivity(); });

function evMeta(action: string) { return actionMeta(action); }

// Группировка по дням (Сегодня / Вчера / дата)
const activityGroups = computed(() => {
  const groups: { key: string; label: string; events: AuditEventRead[] }[] = [];
  const byKey = new Map<string, { key: string; label: string; events: AuditEventRead[] }>();
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const yest = new Date(today); yest.setDate(yest.getDate() - 1);
  for (const ev of activityEvents.value) {
    const d = new Date(ev.created_at);
    const dd = new Date(d); dd.setHours(0, 0, 0, 0);
    const k = `${dd.getFullYear()}-${dd.getMonth()}-${dd.getDate()}`;
    let g = byKey.get(k);
    if (!g) {
      let label: string;
      if (dd.getTime() === today.getTime()) label = t('Сегодня');
      else if (dd.getTime() === yest.getTime()) label = t('Вчера');
      else label = fmt.fmtDate(d, { long: true });
      g = { key: k, label, events: [] };
      byKey.set(k, g); groups.push(g);
    }
    g.events.push(ev);
  }
  return groups;
});

// Раскрытие деталей конкретного события (с подгрузкой AuditEventDetail)
const expandedId = ref<string | null>(null);
const detailCache = ref<Record<string, AuditEventDetail>>({});
const detailLoadingId = ref<string | null>(null);

async function toggleEvent(ev: AuditEventRead) {
  if (expandedId.value === ev.id) { expandedId.value = null; return; }
  expandedId.value = ev.id;
  if (!detailCache.value[ev.id]) {
    detailLoadingId.value = ev.id;
    try {
      detailCache.value = { ...detailCache.value, [ev.id]: await auditApi.eventDetail(ev.id) };
    } catch { /* ignore — покажем то, что есть в строке */ } finally {
      detailLoadingId.value = null;
    }
  }
}

// diff → массив строк {field, from, to} (best-effort под разные формы diff)
function diffRows(diff: Record<string, unknown> | null | undefined): { field: string; from: string; to: string }[] {
  if (!diff || typeof diff !== 'object') return [];
  const out: { field: string; from: string; to: string }[] = [];
  const fmtV = (v: unknown) => v === null || v === undefined ? '—' : (typeof v === 'object' ? JSON.stringify(v) : String(v));
  for (const [field, val] of Object.entries(diff)) {
    if (val && typeof val === 'object' && !Array.isArray(val)) {
      const o = val as Record<string, unknown>;
      const from = 'from' in o ? o.from : ('old' in o ? o.old : ('before' in o ? o.before : undefined));
      const to = 'to' in o ? o.to : ('new' in o ? o.new : ('after' in o ? o.after : undefined));
      if (from !== undefined || to !== undefined) { out.push({ field, from: fmtV(from), to: fmtV(to) }); continue; }
    }
    out.push({ field, from: '', to: fmtV(val) });
  }
  return out;
}

const forcingDisable = ref(false);
async function forceDisableMfa() {
  if (!detail.value) return;
  if (!auth.isOwner) {
    error.value = t('Только владелец платформы может принудительно отключать 2FA');
    return;
  }
  if (!(await confirmDialog({
    message: t('Принудительно отключить 2FA у {email}?\n\nБудет очищено: TOTP-секрет, привязка Telegram, recovery-коды.\nПользователь сможет войти только по паролю. Действие записывается в аудит.', {
      email: detail.value.email,
    }),
    danger: true,
  }))) return;
  forcingDisable.value = true;
  try {
    await adminMfaApi.forceDisable(detail.value.id);
    await loadMfaStatus();
    emit('changed');
  } catch (e: any) {
    error.value = e?.response?.data?.detail || t('Не удалось отключить 2FA');
  } finally {
    forcingDisable.value = false;
  }
}

// Password reset
const showPwdReset = ref(false);
const pwdValue = ref('');
const pwdMustChange = ref(true);
const pwdShown = ref(false);
const pwdSaving = ref(false);
const pwdCopied = ref(false);
const pwdDone = ref(false);   // успешный сброс → показываем пароль для передачи

function openPwdReset() {
  pwdValue.value = generatePassword();
  pwdMustChange.value = true;
  pwdShown.value = true;
  pwdCopied.value = false;
  pwdDone.value = false;
  showPwdReset.value = true;
}
function closePwdReset() {
  showPwdReset.value = false;
  pwdDone.value = false;
  pwdValue.value = '';
  pwdCopied.value = false;
}

async function copyPwd() {
  try {
    await navigator.clipboard.writeText(pwdValue.value);
    pwdCopied.value = true;
    setTimeout(() => (pwdCopied.value = false), 2000);
  } catch {
    /* ignore */
  }
}

async function submitForceChange() {
  if (!detail.value) return;
  if (!(await confirmDialog({
    message: t('Заставить «{name}» сменить пароль при следующем защищённом запросе?\n\nТекущий пароль будет работать только для входа (/auth/login). После входа доступ к любому API закрыт до смены через /change-password.', {
      name: detail.value.full_name || detail.value.email,
    }),
  }))) return;
  try {
    await rbacV3Api.forcePasswordChange(detail.value.id);
    detail.value = await rbacV3Api.getUser(detail.value.id);
    emit('changed');
  } catch (e: any) {
    error.value = e?.response?.data?.detail || t('Не удалось установить флаг');
  }
}

async function submitPwdReset() {
  if (!detail.value || !pwdValue.value) return;
  if (pwdValue.value.length < 12) {
    error.value = t('Пароль должен быть минимум 12 символов');
    return;
  }
  pwdSaving.value = true;
  error.value = null;
  try {
    await rbacV3Api.resetPassword(detail.value.id, pwdValue.value, pwdMustChange.value);
    // Refresh user (must_change_password may have flipped)
    detail.value = await rbacV3Api.getUser(detail.value.id);
    emit('changed');
    // Премиум-UX: НЕ закрываем и НЕ показываем native alert — переходим в
    // success-состояние, где пароль виден и сразу копируется в буфер.
    pwdShown.value = true;
    pwdDone.value = true;
    void copyPwd();
  } catch (e: any) {
    error.value = e?.response?.data?.detail || t('Не удалось сбросить пароль');
  } finally {
    pwdSaving.value = false;
  }
}

// ─── Moderation flags (Pack 148-followup) ────────────────────────
const modSaving = ref(false);
const modOrgDraft = ref('');

async function patchModerationFlag(field: 'is_external' | 'bypass_moderation', value: boolean) {
  if (!detail.value) return;
  modSaving.value = true;
  try {
    await moderationApi.patchUserFlags(detail.value.id, { [field]: value });
    detail.value = { ...detail.value, [field]: value };
    emit('changed');
  } catch (e: any) {
    error.value = e?.response?.data?.detail || t('Не удалось обновить флаг модерации');
  } finally {
    modSaving.value = false;
  }
}

async function patchModerationOrg() {
  if (!detail.value) return;
  modSaving.value = true;
  try {
    await moderationApi.patchUserFlags(detail.value.id, {
      external_org_name: modOrgDraft.value || null,
    });
    detail.value = { ...detail.value, external_org_name: modOrgDraft.value || null };
    emit('changed');
  } catch (e: any) {
    error.value = e?.response?.data?.detail || t('Не удалось сохранить организацию');
  } finally {
    modSaving.value = false;
  }
}

// Initialize draft when detail loads / changes
watch(() => detail.value?.id, () => {
  modOrgDraft.value = detail.value?.external_org_name || '';
});

const showClone = ref(false);
function onCloneCreated(newId: string) {
  emit('changed');
  showClone.value = false;
  emit('open-user', newId);
}

const impersonating = ref(false);
async function startImpersonate() {
  if (!detail.value) return;
  if (!(await confirmDialog({
    message: t('Войти как {email}?\n\nТокен действует 30 минут. После этого вы вернётесь в свой аккаунт.\n\nДействие будет записано в аудит.', {
      email: detail.value.email,
    }),
  }))) return;
  impersonating.value = true;
  try {
    const resp = await createPreviewToken(detail.value.id);
    // Open new tab with preview token in URL — AppShell picks it up and stores
    const url = window.location.origin + '/?preview_token=' + encodeURIComponent(resp.access_token)
              + '&preview_email=' + encodeURIComponent(resp.target_email);
    window.open(url, '_blank');
  } catch (e: any) {
    toast.error(e?.response?.data?.detail || t('Не удалось получить preview-token'));
  } finally {
    impersonating.value = false;
  }
}
const ownerBusy = ref(false);
async function toggleOwner() {
  if (!detail.value) return;
  const grant = !detail.value.is_owner;
  const msg = grant
    ? t('Назначить «{email}» владельцем платформы (OWNER)?\nOWNER получает полный доступ ко всему и может управлять статусом OWNER.', { email: detail.value.email })
    : t('Снять статус OWNER с «{email}»?', { email: detail.value.email });
  if (!(await confirmDialog({ message: msg, danger: true }))) return;
  ownerBusy.value = true; error.value = null;
  try {
    detail.value = await rbacV3Api.setOwner(detail.value.id, grant);
    emit('changed');
  } catch (e: any) {
    error.value = e?.response?.data?.detail || t('Не удалось изменить статус OWNER');
  } finally { ownerBusy.value = false; }
}
async function onDeactivate() {
  if (!detail.value) return;
  if (!(await confirmDialog({
    message: t('Деактивировать пользователя {email}?', { email: detail.value.email }),
    danger: true,
  }))) return;
  try {
    await rbacV3Api.deactivate(detail.value.id);
    emit('changed');
    emit('close');
  } catch (e: any) {
    error.value = e?.response?.data?.detail || t('Ошибка');
  }
}
async function onReactivate() {
  if (!detail.value) return;
  try {
    const updated = await rbacV3Api.reactivate(detail.value.id);
    detail.value = updated;       // дровер остаётся открытым, показывает активный аккаунт
    emit('changed');
  } catch (e: any) {
    error.value = e?.response?.data?.detail || t('Ошибка');
  }
}
async function onDeletePermanent() {
  if (!detail.value) return;
  const input = await promptDialog({
    message: t('Это удалит пользователя НАВСЕГДА.\nВведите email для подтверждения: {email}', {
      email: detail.value.email,
    }),
  });
  if (!input || input.trim().toLowerCase() !== detail.value.email.toLowerCase()) {
    if (input !== null) toast.error(t('Email не совпадает'));
    return;
  }
  try {
    await rbacV3Api.deletePermanent(detail.value.id);
    emit('changed');
    emit('close');
  } catch (e: any) {
    error.value = e?.response?.data?.detail || t('Ошибка');
  }
}
</script>

<template>
  <div v-if="user" class="rv3-drawer">
    <div v-if="loading" class="rv3-loading">{{ t('Загрузка...') }}</div>
    <div v-else-if="error" class="rv3-error">{{ error }}</div>
    <template v-else-if="detail">
      <!-- Header -->
      <div class="rv3-dr-head">
        <div class="rv3-dr-head-top">
          <UserAvatar :email="detail.email" :full-name="detail.full_name" :avatar-url="detail.avatar_url" :size="48" :status="headStatus" />
          <div style="flex:1;min-width:0;">
            <div class="rv3-dr-name">
              {{ detail.full_name }}
              <span class="rv3-dr-presence" :class="'rv3-dr-presence-' + headStatus">{{ t(presenceLabel(headStatus)) }}</span>
            </div>
            <div class="rv3-dr-meta">
              {{ t('{email} · Последний вход: {time}', { email: detail.email, time: lastLoginRelative }) }}
            </div>
          </div>
          <button class="rv3-dr-close" :aria-label="t('Закрыть карточку пользователя')" @click="emit('close')">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>
        <div class="rv3-dr-tabs">
          <button :class="['rv3-dr-tab', { on: tab === 'access' }]" @click="tab = 'access'">{{ t('Доступ') }}</button>
          <button :class="['rv3-dr-tab', { on: tab === 'profile' }]" @click="tab = 'profile'">{{ t('Профиль') }}</button>
          <button :class="['rv3-dr-tab', { on: tab === 'activity' }]" @click="tab = 'activity'">{{ t('Активность') }}</button>
          <button :class="['rv3-dr-tab', { on: tab === 'security' }]" @click="tab = 'security'">{{ t('Безопасность') }}</button>
        </div>
      </div>

      <div class="rv3-dr-body">
        <!-- ACCESS TAB -->
        <div v-if="tab === 'access'">
          <div class="rv3-dr-section">
            <div class="rv3-dr-section-title rv3-dr-section-title-row">
              <span>{{ t('Роли на платформе') }}</span>
              <button
                v-if="canManage && !detail.is_owner && !editingRoles"
                class="rv3-dr-edit-link"
                @click="openRoleEditor"
              >{{ t('Изменить') }}</button>
            </div>
            <!-- Read-only chips -->
            <div v-if="!editingRoles" class="rv3-dr-role-summary">
              <div v-for="rc in detail.role_codes" :key="rc" class="rv3-dr-role-summary-row">
                <RoleChip :code="rc" />
                <span>
                  <b>{{ t(roleLabel(rc)) }}</b>
                  <small v-if="roleByCode[rc]?.description_ru">{{ roleByCode[rc].description_ru }}</small>
                </span>
              </div>
              <span v-if="detail.role_codes.length === 0" class="rv3-empty">{{ t('Нет ролей') }}</span>
            </div>
            <!-- Editor -->
            <div v-else class="rv3-dr-role-editor">
              <RoleAssignmentPicker v-model="draftRoleCodes" :roles="allRoles" compact />
              <div class="rv3-dr-role-foot">
                <span class="rv3-dr-role-warn" v-if="draftRoleCodes.includes('admin')">
                  <!-- Бэкенд отклоняет назначение 'admin' не-владельцем (403), поэтому
                       предупреждение должно называть это до сохранения — как в модалке
                       создания пользователя. -->
                  {{ t('Полный доступ: роль admin снимает ограничения по компаниям и назначается только владельцем платформы.') }}
                </span>
                <button class="rv3-btn rv3-btn-ghost" :disabled="savingRoles" @click="editingRoles = false">{{ t('Отмена') }}</button>
                <button class="rv3-btn rv3-btn-purple" @click="saveRoles" :disabled="savingRoles">
                  {{ savingRoles ? t('Сохранение…') : t('Сохранить роли') }}
                </button>
              </div>
            </div>
          </div>

          <div class="rv3-dr-section">
            <div class="rv3-dr-section-title rv3-dr-section-title-row">
              <span>{{ t('Доступ по компаниям и группам: {count}', {
                count: fmt.fmtNumber((detail.group_memberships || []).length),
              }) }}</span>
              <button
                v-if="canManage && !detail.is_owner && !showAddMembership && availableGroupsForAdd.length"
                class="rv3-dr-edit-link"
                @click="showAddMembership = true"
              >{{ t('Добавить') }}</button>
            </div>

            <!-- Add-membership inline form -->
            <div v-if="showAddMembership" class="rv3-dr-mem-add">
              <div class="rv3-dr-mem-fields">
                <label>
                  <span>{{ t('Компания или группа') }}</span>
                  <select v-model="draftAddGroupId" class="rv3-dr-mem-sel">
                    <option value="">{{ t('Выберите область доступа') }}</option>
                    <option v-for="g in availableGroupsForAdd" :key="g.id" :value="g.id">
                      {{ g.name }}
                    </option>
                  </select>
                </label>
                <label>
                  <span>{{ t('Роль в этой области') }}</span>
                  <select v-model="draftAddRoleCode" class="rv3-dr-mem-sel">
                    <option v-for="r in allRoles" :key="r.code" :value="r.code">{{ r.name_ru }}</option>
                  </select>
                </label>
              </div>
              <div class="rv3-dr-mem-actions">
                <button class="rv3-btn rv3-btn-ghost" :disabled="savingMembership" @click="showAddMembership = false">{{ t('Отмена') }}</button>
                <button class="rv3-btn rv3-btn-purple" @click="addMembership"
                        :disabled="!draftAddGroupId || savingMembership">
                  {{ savingMembership ? t('Добавление…') : t('Добавить доступ') }}
                </button>
              </div>
            </div>

            <div v-if="(detail.group_memberships || []).length === 0 && !showAddMembership && !hasDataScope" class="rv3-empty">
              {{ t('Доступ по компаниям и группам не назначен') }}
            </div>
            <div v-else-if="(detail.group_memberships || []).length" class="rv3-dr-memberships">
              <div
                v-for="m in detail.group_memberships"
                :key="m.group_id"
                class="rv3-dr-mem-row"
              >
                <span class="rv3-dr-mem-grp">
                  <b>{{ m.group_name }}</b>
                  <small>{{ m.role_name || t(roleLabel(m.role_code)) }}</small>
                </span>
                <select
                  v-if="canManage && !detail.is_owner"
                  :value="m.role_code"
                  class="rv3-dr-mem-rolesel"
                  @change="changeMembershipRole(m.group_id, ($event.target as HTMLSelectElement).value)"
                  :title="t('Сменить роль в этой группе')"
                >
                  <option v-for="r in allRoles" :key="r.code" :value="r.code">{{ r.name_ru }}</option>
                </select>
                <RoleChip v-else :code="m.role_code" />
                <button
                  v-if="canManage && !detail.is_owner"
                  class="rv3-dr-mem-x"
                  @click="removeMembership(m.group_id, m.group_name)"
                  :title="t('Убрать из группы')"
                >×</button>
              </div>
            </div>
            <!-- Область доступа к данным: секторы / прямые компании.
                 Показываем блок и когда область ПУСТА, если есть право
                 управлять — иначе секторы нельзя выдать впервые. -->
            <div v-if="hasDataScope || (canManage && !detail.is_owner)" class="rv3-dr-scope">
              <div class="rv3-dr-scope-h rv3-dr-scope-h-row">
                <span>{{ t('Доступ к данным компаний') }}</span>
                <button
                  v-if="canManage && !detail.is_owner && !editingScope"
                  class="rv3-dr-edit-link"
                  @click="openScopeEditor"
                >{{ t('Изменить') }}</button>
              </div>

              <!-- Режим правки: чекбоксы секторов -->
              <div v-if="editingScope" class="rv3-dr-scope-edit">
                <label v-for="sec in allSectors" :key="'edit-' + sec.code" class="rv3-dr-scope-opt">
                  <input type="checkbox"
                         :checked="draftSectors.includes(sec.code)"
                         @change="toggleSector(sec.code)" />
                  <span class="rv3-dr-scope-dot" :style="{ background: sec.color_hex || '#7F77DD' }"></span>
                  <span>{{ sec.name_ru || sec.code }}</span>
                </label>
                <div v-if="!allSectors.length" class="rv3-dr-scope-note">{{ t('Справочник секторов не загружен.') }}</div>
                <div class="rv3-dr-scope-actions">
                  <button class="rv3-btn rv3-btn-ghost" :disabled="savingScope"
                          @click="editingScope = false">{{ t('Отмена') }}</button>
                  <button class="rv3-btn rv3-btn-purple" :disabled="savingScope" @click="saveScope">
                    {{ savingScope ? t('Сохранение…') : t('Сохранить') }}
                  </button>
                </div>
                <div class="rv3-dr-scope-note">
                  {{ t('Пусто: доступ по секторам снят, компании из групп при этом остаются.') }}
                </div>
              </div>

              <div v-else-if="!hasDataScope" class="rv3-dr-scope-note">
                {{ t('Область по секторам не задана: доступ определяется группами компаний.') }}
              </div>
              <div v-else class="rv3-dr-scope-chips">
                <span v-for="s in (detail.allowed_sectors || [])" :key="'sec-' + s"
                      class="rv3-dr-scope-chip"
                      :style="{ color: sectorColor(s), background: sectorColor(s) + '14', borderColor: sectorColor(s) + '33' }"
                      :title="t('Доступ ко всем компаниям сектора «{sector}»', { sector: sectorLabel(s) })">
                  <span class="rv3-dr-scope-dot" :style="{ background: sectorColor(s) }"></span>
                  {{ t('Сектор: {sector}', { sector: sectorLabel(s) }) }}
                </span>
                <span v-for="c in (detail.allowed_companies || [])" :key="'co-' + c"
                      class="rv3-dr-scope-chip rv3-dr-scope-chip-co">{{ c }}</span>
              </div>
              <div v-if="(detail.allowed_sectors || []).length" class="rv3-dr-scope-note">
                {{ t('Пользователь видит все компании выбранных секторов.') }}
              </div>
            </div>

            <div v-if="!canManage" class="rv3-dr-mem-hint">
              {{ t('Для редактирования членства нужны права admin.users.') }}
            </div>
          </div>

          <div class="rv3-dr-section">
            <div class="rv3-dr-section-title rv3-dr-section-title-row">
              <span>{{ t('Доступ к модулям: {count} из {total}', {
                count: fmt.fmtNumber(accessCount),
                total: fmt.fmtNumber(MODULE_REGISTRY.length),
              }) }}</span>
              <button
                v-if="canManage && !detail.is_owner && !editingAccess"
                class="rv3-dr-edit-link"
                @click="openAccessEditor"
              >{{ t('Изменить') }}</button>
            </div>
            <ModuleSelectGrid
              v-if="!editingAccess"
              :model-value="access.levels"
              :sources="access.sources"
              :columns="2"
            />
            <template v-else>
              <ModuleSelectGrid
                :model-value="draftLevels"
                :editable="true"
                :columns="2"
                @update:modelValue="(v) => draftLevels = v"
              />
              <div class="rv3-dr-acc-hint">
                {{ t('Изменения сохраняются как персональные права поверх ролей: повышение — grant, понижение — deny. Это влияет только на данного пользователя. Администрирование платформы выдаётся ролью.') }}
              </div>
              <div class="rv3-dr-role-foot">
                <div style="flex:1"></div>
                <button class="rv3-btn rv3-btn-ghost" :disabled="savingAccess" @click="cancelAccessEditor">{{ t('Отмена') }}</button>
                <button class="rv3-btn rv3-btn-purple" @click="saveAccess" :disabled="savingAccess">
                  {{ savingAccess ? t('Сохранение…') : t('Сохранить доступ') }}
                </button>
              </div>
            </template>
            <!-- Две ступени доступа: цвета совпадают с полосой карточки модуля. -->
            <div v-if="!editingAccess" class="rv3-legend">
              <span><span class="rv3-sw" style="background:#7C6FF7"></span>{{ t("Редактировать") }}</span>
              <span><span class="rv3-sw" style="background:#0891B2"></span>{{ t("Наблюдать") }}</span>
              <span><span class="rv3-sw" style="background:#D1D5DB"></span>{{ t("Нет доступа") }}</span>
            </div>
          </div>
        </div>

        <!-- PROFILE TAB -->
        <div v-else-if="tab === 'profile'">
          <div class="rv3-dr-section">
            <div class="rv3-dr-section-title">
              {{ t('Профиль') }}
              <button v-if="!editingProfile" class="rv3-prof-edit" @click="openProfileEditor">{{ t('Редактировать') }}</button>
            </div>
            <!-- Read-only -->
            <template v-if="!editingProfile">
              <div class="rv3-prof-row"><span class="rv3-prof-l">{{ t('ФИО') }}</span><span>{{ detail.full_name }}</span></div>
              <div class="rv3-prof-row"><span class="rv3-prof-l">{{ t('Email') }}</span><span>{{ detail.email }}</span></div>
              <div class="rv3-prof-row"><span class="rv3-prof-l">{{ t('Должность') }}</span><span>{{ detail.job_title || '—' }}</span></div>
              <div class="rv3-prof-row"><span class="rv3-prof-l">{{ t('Отдел') }}</span><span>{{ detail.department || '—' }}</span></div>
              <div class="rv3-prof-row"><span class="rv3-prof-l">{{ t('Компания') }}</span><span>{{ companyName(detail.organization_id) }}</span></div>
            </template>
            <!-- Admin edit -->
            <template v-else>
              <div class="rv3-prof-edit-grid">
                <label class="rv3-pe-field"><span>{{ t('ФИО') }}</span><input v-model="profForm.full_name" class="rv3-pe-in" /></label>
                <label class="rv3-pe-field"><span>{{ t('Должность') }}</span><input v-model="profForm.job_title" class="rv3-pe-in" :placeholder="t('Финансовый аналитик')" /></label>
                <label class="rv3-pe-field"><span>{{ t('Отдел') }}</span><input v-model="profForm.department" class="rv3-pe-in" :placeholder="t('Финансовый блок')" /></label>
                <label class="rv3-pe-field"><span>{{ t('Компания') }}</span>
                  <select v-model="profForm.organization_id" class="rv3-pe-in">
                    <option value="">— {{ t('Не указана') }}</option>
                    <option v-for="c in allCompanies" :key="c.id" :value="c.id">{{ c.name }}</option>
                  </select>
                </label>
              </div>
              <div class="rv3-pe-actions">
                <button class="rv3-pe-cancel" :disabled="savingProfile" @click="editingProfile = false">{{ t('Отмена') }}</button>
                <button class="rv3-pe-save" :disabled="savingProfile" @click="saveProfile">{{ savingProfile ? t('Сохранение…') : t('Сохранить') }}</button>
              </div>
            </template>
            <div class="rv3-prof-row"><span class="rv3-prof-l">{{ t('Создан') }}</span><span>{{ fmt.fmtDate(detail.created_at) }}</span></div>
            <div class="rv3-prof-row"><span class="rv3-prof-l">{{ t('Статус') }}</span><span :style="{ color: detail.is_active ? '#1D9E75' : '#E24B4A' }">{{ detail.is_active ? t('Активен') : t('Заблокирован') }}</span></div>
            <div v-if="detail.is_owner" class="rv3-prof-row"><span class="rv3-prof-l">{{ t('Особое') }}</span><span style="color:#B27015;font-weight:500;">{{ t('Владелец платформы (OWNER)') }}</span></div>
            <!-- OWNER может назначать/снимать статус OWNER (бэк гейтит owner-only) -->
            <div class="rv3-prof-row" v-if="auth.isOwner && detail.id !== auth.user?.id">
              <span class="rv3-prof-l">OWNER</span>
              <button class="rv3-owner-toggle" :class="{ on: detail.is_owner }" :disabled="ownerBusy" @click="toggleOwner">
                {{ ownerBusy ? '…' : (detail.is_owner ? t('✓ Снять статус OWNER') : t('Назначить OWNER')) }}
              </button>
            </div>
          </div>
        </div>

        <!-- ACTIVITY TAB -->
        <div v-else-if="tab === 'activity'">
          <!-- Последний вход -->
          <div class="rv3-dr-section">
            <div class="rv3-dr-section-title">{{ t('Вход в систему') }}</div>
            <div class="rv3-prof-row">
              <span class="rv3-prof-l">{{ t('Последний вход') }}</span>
              <span>
                {{ detail.last_login_at ? fmt.fmtDateTime(detail.last_login_at) : '—' }}
                <span v-if="(detail as any).last_login_ip" style="color: var(--t3, #888780)">· {{ (detail as any).last_login_ip }}</span>
                <span v-if="detail.last_login_at" style="color: var(--t3, #888780)"> · {{ lastLoginRelative }}</span>
              </span>
            </div>
          </div>

          <!-- История действий (аудит) -->
          <div class="rv3-dr-section">
            <div class="rv3-dr-section-title rv3-dr-section-title-row">
              <span>{{ t('История действий') }}</span>
              <span v-if="activityEvents.length" class="rv3-act-count">{{ fmt.fmtNumber(activityEvents.length) }}</span>
            </div>

            <div v-if="activityLoading" class="rv3-empty">{{ t('Загрузка истории…') }}</div>
            <div v-else-if="activityDenied" class="rv3-empty">{{ t('Для просмотра истории нужно право audit.view.') }}</div>
            <div v-else-if="!activityEvents.length" class="rv3-empty">{{ t('Действий пока нет.') }}</div>

            <div v-else class="rv3-act-groups">
              <div v-for="grp in activityGroups" :key="grp.key" class="rv3-act-group">
                <div class="rv3-act-daylbl">{{ t(grp.label) }}<span class="rv3-act-daycnt">{{ grp.events.length }}</span></div>
                <div class="rv3-act-list">
                  <div v-for="ev in grp.events" :key="ev.id" class="rv3-act-item" :class="{ open: expandedId === ev.id }">
                    <button class="rv3-act-row" @click="toggleEvent(ev)">
                      <span class="rv3-act-dot" :style="{ background: evMeta(ev.action).color }"></span>
                      <div class="rv3-act-body">
                        <div class="rv3-act-top">
                          <span class="rv3-act-action" :style="{ color: evMeta(ev.action).color }">{{ t(evMeta(ev.action).label) }}</span>
                          <span v-if="ev.is_critical" class="rv3-act-crit">{{ t('Критическое') }}</span>
                          <span v-if="ev.entity_label" class="rv3-act-entity">{{ ev.entity_label }}</span>
                        </div>
                        <div class="rv3-act-meta">
                          {{ fmt.fmtDateTime(ev.created_at) }}
                          <span v-if="ev.module"> · {{ ev.module }}</span>
                          <span v-if="ev.http_status"> · {{ ev.http_status }}</span>
                          <span v-if="ev.ip_address"> · {{ ev.ip_address }}</span>
                        </div>
                      </div>
                      <svg class="rv3-act-caret" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="9 18 15 12 9 6"/></svg>
                    </button>

                    <!-- Подробности -->
                    <div v-if="expandedId === ev.id" class="rv3-act-detail">
                      <div v-if="detailLoadingId === ev.id" class="rv3-empty">{{ t('Загрузка деталей…') }}</div>
                      <template v-else>
                        <div class="rv3-act-dl">
                          <div v-if="ev.http_method || ev.http_path" class="rv3-act-drow">
                            <span class="rv3-act-dk">{{ t('Запрос') }}</span>
                            <span class="rv3-act-dv mono"><b>{{ ev.http_method }}</b> {{ ev.http_path }}<span v-if="ev.http_status"> → {{ ev.http_status }}</span><span v-if="ev.duration_ms"> · {{ t('{duration} мс', { duration: fmt.fmtNumber(ev.duration_ms) }) }}</span></span>
                          </div>
                          <div v-if="ev.entity_type || ev.entity_id" class="rv3-act-drow">
                            <span class="rv3-act-dk">{{ t('Объект') }}</span>
                            <span class="rv3-act-dv">{{ ev.entity_type }}<span v-if="ev.entity_id" class="mono"> · {{ String(ev.entity_id).slice(0, 8) }}</span></span>
                          </div>
                          <div v-if="ev.actor_role" class="rv3-act-drow"><span class="rv3-act-dk">{{ t('Роль') }}</span><span class="rv3-act-dv">{{ ev.actor_role }}</span></div>
                          <div v-if="detailCache[ev.id]?.notes" class="rv3-act-drow"><span class="rv3-act-dk">{{ t('Заметка') }}</span><span class="rv3-act-dv">{{ detailCache[ev.id]?.notes }}</span></div>
                          <div v-if="detailCache[ev.id]?.user_agent" class="rv3-act-drow"><span class="rv3-act-dk">{{ t('Устройство') }}</span><span class="rv3-act-dv rv3-act-ua">{{ detailCache[ev.id]?.user_agent }}</span></div>
                        </div>

                        <!-- Изменения (diff) -->
                        <div v-if="diffRows(detailCache[ev.id]?.diff).length" class="rv3-act-diff">
                          <div class="rv3-act-difflbl">{{ t('Изменения') }}</div>
                          <div v-for="(dr, i) in diffRows(detailCache[ev.id]?.diff)" :key="i" class="rv3-act-diffrow">
                            <span class="rv3-act-diff-f">{{ dr.field }}</span>
                            <span class="rv3-act-diff-v"><span v-if="dr.from" class="rv3-act-diff-old">{{ dr.from }}</span><span v-if="dr.from" class="rv3-act-diff-arr">→</span><span class="rv3-act-diff-new">{{ dr.to }}</span></span>
                          </div>
                        </div>
                      </template>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- SECURITY TAB -->
        <div v-else-if="tab === 'security'">

          <!-- ── Password ── -->
          <div class="rv3-dr-section">
            <div class="rv3-dr-section-title rv3-dr-section-title-row">
              <span>{{ t('Пароль') }}</span>
              <div v-if="canManage && !detail.is_owner && !showPwdReset" class="rv3-dr-pwd-actions">
                <button
                  v-if="!detail.must_change_password"
                  class="rv3-dr-edit-link"
                  @click="submitForceChange"
                  :title="t('Установить флаг must_change_password=true без смены пароля')"
                ><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>{{ t('Заставить сменить') }}</button>
                <button class="rv3-dr-edit-link" @click="openPwdReset"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="7.5" cy="15.5" r="5.5"/><path d="M11.4 11.6 21 2l-2 2 2 2-3 3-2-2"/></svg>{{ t('Сбросить') }}</button>
              </div>
            </div>
            <div v-if="!showPwdReset" class="rv3-prof-row">
              <span class="rv3-prof-l">{{ t('Статус') }}</span>
              <span :class="{ 'rv3-status-warn': detail.must_change_password }">
                {{ detail.must_change_password ? t('⚠ Требуется смена при следующем входе') : t('✓ Действителен') }}
              </span>
            </div>
            <div v-if="!showPwdReset && (detail as any).password_changed_at" class="rv3-prof-row">
              <span class="rv3-prof-l">{{ t('Последняя смена') }}</span>
              <span class="rv3-status-mono">{{ fmt.fmtDateTime((detail as any).password_changed_at) }}</span>
            </div>

            <div v-else class="rv3-dr-pwd-panel" :class="{ 'rv3-dr-pwd-panel-done': pwdDone }">
              <!-- До сброса: подсказка -->
              <div v-if="!pwdDone" class="rv3-dr-pwd-hint">
                {{ t('Сгенерирован новый пароль. После сброса он применяется немедленно, а все активные сессии этого пользователя завершаются.') }}
              </div>
              <!-- После сброса: success -->
              <div v-else class="rv3-dr-pwd-success">
                <span class="rv3-dr-pwd-success-ic"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12l5 5L20 6"/></svg></span>
                <div>
                  <div class="rv3-dr-pwd-success-t">{{ t('Пароль сброшен · скопирован в буфер') }}</div>
                  <div class="rv3-dr-pwd-success-s">{{ pwdMustChange
                    ? t('Сессии пользователя завершены · потребуется смена при входе.')
                    : t('Сессии пользователя завершены.') }}</div>
                </div>
              </div>

              <div class="rv3-dr-pwd-row">
                <input
                  :type="pwdShown ? 'text' : 'password'"
                  v-model="pwdValue"
                  class="rv3-dr-pwd-input"
                  :readonly="pwdDone"
                  autocomplete="new-password"
                  name="rv3-new-pwd"
                  data-lpignore="true"
                  data-1p-ignore
                />
                <button class="rv3-dr-pwd-mini" :title="pwdShown ? t('Скрыть') : t('Показать')" @click="pwdShown = !pwdShown">
                  <svg v-if="pwdShown" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19M1 1l22 22"/></svg>
                  <svg v-else width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
                </button>
                <button v-if="!pwdDone" class="rv3-dr-pwd-mini" :title="t('Сгенерировать новый')" @click="pwdValue = generatePassword()"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M23 4v6h-6M1 20v-6h6"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg></button>
                <button class="rv3-dr-pwd-mini" :class="{ 'rv3-dr-pwd-mini-ok': pwdCopied }" :title="pwdCopied ? t('Скопировано') : t('Скопировать')" @click="copyPwd">
                  {{ pwdCopied ? '✓' : '⧉' }}
                </button>
              </div>

              <label v-if="!pwdDone" class="rv3-dr-pwd-check">
                <input type="checkbox" v-model="pwdMustChange"/>
                {{ t('Требовать смену пароля при следующем входе') }}
              </label>

              <div class="rv3-dr-role-foot">
                <span class="rv3-dr-pwd-warn">{{ t('⚠ Передайте пароль безопасным каналом (не в email).') }}</span>
                <template v-if="!pwdDone">
                  <button class="rv3-btn rv3-btn-ghost" :disabled="pwdSaving" @click="closePwdReset">{{ t('Отмена') }}</button>
                  <button class="rv3-btn rv3-btn-purple" @click="submitPwdReset"
                          :disabled="pwdSaving || !pwdValue || pwdValue.length < 12">
                    {{ pwdSaving ? t('Сброс…') : t('Сбросить пароль') }}
                  </button>
                </template>
                <button v-else class="rv3-btn rv3-btn-purple" @click="closePwdReset">{{ t('Готово') }}</button>
              </div>
            </div>
          </div>

          <!-- ── MFA ── -->
          <div class="rv3-dr-section">
            <div class="rv3-dr-section-title rv3-dr-section-title-row">
              <span>{{ t('Двухфакторная аутентификация') }}</span>
              <button
                v-if="auth.isOwner && !detail.is_owner && mfaRow?.mfa_enabled"
                class="rv3-dr-edit-link rv3-dr-edit-link-danger"
                @click="forceDisableMfa"
                :disabled="forcingDisable"
              >{{ forcingDisable ? '…' : t('Сбросить 2FA') }}</button>
            </div>

            <div v-if="mfaLoading" class="rv3-empty">{{ t('Загрузка статуса…') }}</div>
            <div v-else-if="!mfaRow" class="rv3-empty">{{ t('Статус недоступен') }}</div>
            <div v-else>
              <div class="rv3-prof-row">
                <span class="rv3-prof-l">MFA</span>
                <span :style="{ color: mfaRow.mfa_enabled ? '#1D9E75' : '#E24B4A' }">
                  {{ mfaRow.mfa_enabled ? t('Включена') : t('Отключена') }}
                  <span v-if="mfaRow.mfa_enabled" style="color: var(--t3, #888780)">· {{ mfaRow.mfa_method }}</span>
                </span>
              </div>
              <div class="rv3-prof-row">
                <span class="rv3-prof-l">Telegram</span>
                <span>
                  <template v-if="mfaRow.telegram_linked">
                    @{{ mfaRow.telegram_username || '—' }}
                    <span style="color: var(--t3, #888780)" v-if="mfaRow.telegram_linked_at">
                      · {{ t('с {date}', { date: fmt.fmtDate(mfaRow.telegram_linked_at) }) }}
                    </span>
                  </template>
                  <span v-else style="color: var(--t3, #888780)">{{ t('Не привязан') }}</span>
                </span>
              </div>
              <div class="rv3-prof-row">
                <span class="rv3-prof-l">{{ t('Recovery-коды') }}</span>
                <span :style="{ color: mfaRow.recovery_codes_remaining > 2 ? '#1D9E75' : (mfaRow.recovery_codes_remaining > 0 ? '#EF9F27' : '#E24B4A') }">
                  {{ t('Осталось: {count}', { count: fmt.fmtNumber(mfaRow.recovery_codes_remaining) }) }}
                </span>
              </div>
              <div class="rv3-prof-row" v-if="mfaRow.last_login_at">
                <span class="rv3-prof-l">{{ t('Последний вход') }}</span>
                <span>
                  {{ fmt.fmtDateTime(mfaRow.last_login_at) }}
                  <span v-if="mfaRow.last_login_ip" style="color: var(--t3, #888780)">· {{ mfaRow.last_login_ip }}</span>
                </span>
              </div>

              <div v-if="!auth.isOwner && mfaRow.mfa_enabled" class="rv3-dr-mem-hint">
                {{ t('Сбросить 2FA пользователя может только владелец платформы.') }}
              </div>
              <div v-if="!mfaRow.mfa_enabled" class="rv3-dr-mem-hint">
                {{ t('Пользователь не настроил 2FA. Настройка доступна пользователю в профиле.') }}
              </div>
            </div>
          </div>

          <!-- ── Moderation flags (Pack 148-followup) ── -->
          <div class="rv3-dr-section">
            <div class="rv3-dr-section-title">{{ t('Модерация') }}</div>
            <div v-if="!canManage" class="rv3-dr-mem-hint">
              {{ t('Управление флагами модерации требует право admin.users.') }}
            </div>
            <div v-else-if="detail.is_owner" class="rv3-dr-mem-hint">
              {{ t('Владелец платформы всегда обходит модерацию.') }}
            </div>
            <div v-else>
              <div class="rv3-dr-mod-row">
                <span class="rv3-dr-mod-lbl">
                  <span class="rv3-dr-mod-name">{{ t('External (внешний пользователь)') }}</span>
                  <span class="rv3-dr-mod-hint">
                    {{ t('Включает сопоставление по правилам с {flag}.', { flag: 'trigger_is_external=true' }) }}
                  </span>
                </span>
                <label class="rv3-dr-mod-switch">
                  <input
                    type="checkbox"
                    :checked="detail.is_external"
                    :disabled="modSaving"
                    @change="patchModerationFlag('is_external', ($event.target as HTMLInputElement).checked)"
                  />
                  <span class="rv3-dr-mod-tr"></span>
                </label>
              </div>

              <div class="rv3-dr-mod-row">
                <span class="rv3-dr-mod-lbl">
                  <span class="rv3-dr-mod-name">{{ t('Bypass moderation (обход)') }}</span>
                  <span class="rv3-dr-mod-hint">
                    {{ t('Запись идёт напрямую, даже если правило совпало.') }}
                  </span>
                </span>
                <label class="rv3-dr-mod-switch">
                  <input
                    type="checkbox"
                    :checked="detail.bypass_moderation"
                    :disabled="modSaving"
                    @change="patchModerationFlag('bypass_moderation', ($event.target as HTMLInputElement).checked)"
                  />
                  <span class="rv3-dr-mod-tr"></span>
                </label>
              </div>

              <div v-if="detail.is_external" class="rv3-dr-mod-row rv3-dr-mod-row-input">
                <span class="rv3-dr-mod-lbl">
                  <span class="rv3-dr-mod-name">{{ t('Организация') }}</span>
                  <span class="rv3-dr-mod-hint">{{ t('Видна в списке «Подмодерируемые».') }}</span>
                </span>
                <div class="rv3-dr-mod-input-wrap">
                  <input
                    v-model="modOrgDraft"
                    class="rv3-dr-mod-input"
                    :placeholder="t('напр. АО Контрагент')"
                    @blur="patchModerationOrg"
                    @keydown.enter="patchModerationOrg"
                    :disabled="modSaving"
                  />
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Footer actions -->
      <div class="rv3-dr-foot" v-if="!detail.is_owner">
        <button class="rv3-btn rv3-btn-purple" @click="showClone = true">{{ t('Создать аналогичного') }}</button>
        <button
          v-if="detail.is_active && !detail.role_codes.includes('admin') && !detail.role_codes.includes('ceo')"
          class="rv3-btn rv3-btn-ghost rv3-btn-imp"
          @click="startImpersonate"
          :disabled="impersonating"
          :title="t('Открыть платформу глазами этого пользователя (30 мин)')"
        >
          <svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><circle cx="8" cy="5" r="2.5"/><path d="M3 13c0-2.5 2-4 5-4s5 1.5 5 4"/></svg>
          {{ impersonating ? t('Загрузка...') : t('Войти как') }}
        </button>
        <div style="flex:1;"></div>
        <button
          v-if="canManage && (!detail.is_active || isLocked)"
          class="rv3-btn rv3-btn-green"
          @click="onReactivate"
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 9.9-1"/></svg>
          {{ !detail.is_active ? t('Активировать') : t('Разблокировать') }}
        </button>
        <button v-if="detail.is_active" class="rv3-btn rv3-btn-ghost" @click="onDeactivate">{{ t('Деактивировать') }}</button>
        <button class="rv3-btn rv3-btn-red" @click="onDeletePermanent">{{ t('Удалить') }}</button>
      </div>
    </template>

    <InviteUserModal
      v-if="showClone && detail"
      :prefill="{ full_name: '', department: detail.department || undefined, role_codes: detail.role_codes }"
      @close="showClone = false"
      @created="onCloneCreated"
    />
  </div>
</template>

<style scoped>
.rv3-drawer {
  width: 540px;
  background: var(--bg1, #fff);
  display: flex;
  flex-direction: column;
  height: 100%;
  border-left: 0.5px solid var(--border-hard);
}
.rv3-loading, .rv3-error {
  padding: 40px;
  text-align: center;
  color: var(--t3, var(--t-muted));
  font-size: 13px;
}
.rv3-error { color: var(--sev-high); }

.rv3-dr-head { padding: 18px 22px 0; border-bottom: 0.5px solid var(--border-hard); }
.rv3-dr-head-top { display: flex; align-items: center; gap: 14px; margin-bottom: 14px; }
.rv3-dr-name { font-size: 16px; font-weight: 500; letter-spacing: -.01em; }
.rv3-dr-meta { font-size: 11px; color: var(--t3, var(--t-muted)); margin-top: 3px; }
/* Presence-подпись рядом с именем в шапке дровера */
.rv3-dr-presence {
  display: inline-flex; align-items: center;
  margin-left: 8px;
  padding: 1px 8px; border-radius: 999px;
  font-size: 10px; font-weight: 600; letter-spacing: .02em;
  vertical-align: middle;
}
.rv3-dr-presence-online  { background: rgba(29,158,117,.12); color: #0F6E56; }
.rv3-dr-presence-away    { background: rgba(239,159,39,.14); color: #B87600; }
.rv3-dr-presence-offline { background: rgba(30,42,74,.07);  color: var(--t3, #94A3B8); }
.rv3-dr-close {
  width: 30px; height: 30px;
  background: transparent; border: none; cursor: pointer;
  color: var(--t3, var(--t-muted)); border-radius: 6px;
  display: flex; align-items: center; justify-content: center;
}
.rv3-dr-close:hover { background: #F3F4F8; color: var(--t1, #1E2A4A); }

.rv3-dr-tabs { display: flex; gap: 0; }
.rv3-dr-tab {
  padding: 9px 14px;
  font-size: 12px; font-weight: 500;
  color: var(--t3, var(--t-muted));
  background: transparent; border: none; border-bottom: 2px solid transparent;
  cursor: pointer; font-family: inherit;
}
.rv3-dr-tab:hover { color: var(--t1, #1E2A4A); }
.rv3-dr-tab.on { color: var(--t1, #1E2A4A); border-bottom-color: #7F77DD; }

.rv3-dr-body { flex: 1; overflow-y: auto; padding: 18px 22px; }

.rv3-dr-section { margin-bottom: 18px; }
.rv3-dr-section-title {
  font-size: 10px; font-weight: 500; color: var(--t3, var(--t-muted));
  letter-spacing: .06em; text-transform: uppercase;
  margin-bottom: 8px;
}
.rv3-dr-section-title-row {
  display: flex; align-items: center; justify-content: space-between;
}
.rv3-dr-chips { display: flex; gap: 6px; flex-wrap: wrap; }
.rv3-dr-role-summary {
  display: flex;
  flex-direction: column;
  border-top: 1px solid var(--border-hard, #E5E7EB);
}
.rv3-dr-role-summary-row {
  min-height: 48px;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: center;
  gap: 10px;
  padding: 7px 2px;
  border-bottom: 1px solid var(--border-hard, #E5E7EB);
}
.rv3-dr-role-summary-row > span:last-child {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.rv3-dr-role-summary-row b {
  color: var(--t1, #1E2A4A);
  font-size: 11.5px;
  font-weight: 600;
}
.rv3-dr-role-summary-row small {
  overflow: hidden;
  color: var(--t3, var(--t-muted));
  font-size: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.rv3-dr-scope {
  background: var(--bg2, #FAFAFC); border: 0.5px solid var(--border-hard); border-radius: 8px;
  padding: 10px 12px; font-size: 11.5px; color: var(--t1, #1E2A4A);
}
.rv3-empty {
  font-size: 11.5px; color: var(--t3, var(--t-muted));
  font-style: italic;
}
.rv3-dr-memberships {
  display: flex; flex-direction: column; gap: 4px;
  background: var(--bg2, #FAFAFC); border: 0.5px solid var(--border-hard); border-radius: 8px;
  padding: 8px 10px;
}
.rv3-dr-mem-row {
  display: flex; align-items: center; gap: 10px;
  min-height: 42px; padding: 5px 0; font-size: 12px; color: var(--t1, #1E2A4A);
}
.rv3-dr-mem-row:not(:last-child) {
  border-bottom: 0.5px solid #F0F0F4;
}
.rv3-dr-mem-grp {
  min-width: 0; flex: 1; display: flex; flex-direction: column; gap: 2px;
}
.rv3-dr-mem-grp b { overflow: hidden; font-size: 11.5px; font-weight: 600; text-overflow: ellipsis; white-space: nowrap; }
.rv3-dr-mem-grp small { color: var(--t3, var(--t-muted)); font-size: 9.5px; }
.rv3-dr-mem-co-badge {
  font-size: 8.5px; color: var(--green);
  background: rgba(29,158,117,.1);
  padding: 1px 5px; border-radius: 3px;
  font-weight: 500; letter-spacing: .04em; text-transform: uppercase;
}
.rv3-dr-mem-hint {
  margin-top: 6px; font-size: 10.5px; color: var(--t3, var(--t-muted));
  font-style: italic;
}
.rv3-dr-scope { margin-top: 12px; }
.rv3-dr-scope-h {
  font-size: 10px; font-weight: 500; text-transform: uppercase; letter-spacing: 0.06em;
  color: var(--t3, var(--t-muted)); margin-bottom: 8px;
}
.rv3-dr-scope-chips { display: flex; flex-wrap: wrap; gap: 6px; }
.rv3-dr-scope-chip {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 11.5px; font-weight: 500;
  padding: 3px 10px; border-radius: 8px;
  border: 1px solid var(--border-hard, #E5E7EB);
}
.rv3-dr-scope-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
.rv3-dr-scope-chip-co { color: var(--t2, #475569); background: var(--bg2, #FAFAFC); }
.rv3-dr-scope-note { margin-top: 8px; font-size: 10.5px; color: var(--t3, var(--t-muted)); }
/* Редактор области доступа по секторам (чекбоксы + действия) */
.rv3-dr-scope-h-row { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.rv3-dr-scope-edit { display: flex; flex-direction: column; gap: 6px; margin-top: 8px; }
.rv3-dr-scope-opt {
  display: flex; align-items: center; gap: 8px;
  font-size: 12px; color: var(--t1, #1e2a4a);
  padding: 5px 7px; border-radius: 7px; cursor: pointer;
}
.rv3-dr-scope-opt:hover { background: rgba(127, 119, 221, .07); }
.rv3-dr-scope-opt input { cursor: pointer; }
.rv3-dr-scope-actions { display: flex; gap: 8px; margin-top: 4px; }
.rv3-legend {
  margin-top: 12px;
  display: flex; gap: 14px; flex-wrap: wrap;
  font-size: 9.5px; color: var(--t3, var(--t-muted));
}
.rv3-legend span { display: flex; align-items: center; gap: 5px; }
.rv3-sw { width: 8px; height: 8px; border-radius: 2px; }
.rv3-prof-row {
  display: flex; gap: 12px; padding: 6px 0;
  font-size: 12px; border-bottom: 0.5px solid #F3F4F8;
}
.rv3-prof-l { color: var(--t3, var(--t-muted)); width: 110px; flex-shrink: 0; }
.rv3-prof-edit { float: right; border: none; background: rgba(124,111,247,.12); color: #534AB7; font-size: 10.5px; font-weight: 600; border-radius: 999px; padding: 3px 10px; cursor: pointer; font-family: var(--font); }
.rv3-prof-edit:hover { background: rgba(124,111,247,.22); }
.rv3-prof-edit-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 9px; margin: 8px 0; }
.rv3-pe-field { display: flex; flex-direction: column; gap: 4px; font-size: 10.5px; color: var(--t3, #94A3B8); }
.rv3-pe-in { border: 1px solid rgba(99,102,180,.18); border-radius: 8px; padding: 6px 9px; font-size: 12.5px; font-family: var(--font); color: var(--t1, #0F172A); outline: none; }
.rv3-pe-in:focus { border-color: #7C6FF7; }
.rv3-pe-actions { display: flex; justify-content: flex-end; gap: 8px; margin: 6px 0 10px; }
.rv3-pe-cancel { border: 1px solid rgba(99,102,180,.18); background: #fff; color: #64748B; border-radius: 8px; padding: 6px 14px; font-size: 12px; cursor: pointer; font-family: var(--font); }
.rv3-pe-save { border: none; background: linear-gradient(135deg,#7C6FF7,#534AB7); color: #fff; border-radius: 8px; padding: 6px 16px; font-size: 12px; font-weight: 600; cursor: pointer; font-family: var(--font); }
.rv3-pe-save:disabled { opacity: .6; cursor: default; }
.rv3-owner-toggle {
  padding: 4px 12px; border-radius: 7px; font-size: 11.5px; font-weight: 600;
  border: 1px solid rgba(178,112,21,.35); background: rgba(178,112,21,.08);
  color: #B27015; cursor: pointer; font-family: inherit; transition: all .14s;
}
.rv3-owner-toggle:hover:not(:disabled) { background: rgba(178,112,21,.16); }
.rv3-owner-toggle.on { border-color: rgba(226,75,74,.4); background: rgba(226,75,74,.08); color: #C0392B; }
.rv3-owner-toggle:disabled { opacity: .6; cursor: default; }

.rv3-dr-foot {
  padding: 14px 22px;
  background: var(--bg2, #FAFAFC);
  border-top: 0.5px solid var(--border-hard);
  display: flex; gap: 8px; align-items: center;
}
.rv3-btn {
  padding: 7px 12px; border-radius: 8px;
  font-size: 11px; font-weight: 500; font-family: inherit;
  cursor: pointer;
}
.rv3-btn-purple {
  background: var(--p-deep); border: none; color: #fff;
}
.rv3-btn-purple:hover { background: #463E9F; }
.rv3-btn-ghost {
  background: transparent; border: 1px solid var(--border-hard); color: var(--t1, #1E2A4A);
}
.rv3-btn-ghost:hover { background: #F3F4F8; }
.rv3-btn-red {
  background: var(--bg1, #fff); border: 1px solid var(--sev-high); color: var(--sev-high);
}
.rv3-btn-red:hover { background: rgba(226,75,74,.06); }
.rv3-btn-green {
  display: flex; align-items: center; gap: 5px;
  background: #1D9E75; border: none; color: #fff;
}
.rv3-btn-green:hover { background: #178B66; }
.rv3-btn-imp {
  display: flex; align-items: center; gap: 5px;
  color: var(--p-deep) !important; border-color: rgba(127,119,221,.4) !important;
}
.rv3-btn-imp:hover { background: rgba(127,119,221,.06); }
.rv3-btn-imp:disabled { opacity: .55; cursor: not-allowed; }

/* Pack 148-followup: in-place role + membership editor */
.rv3-dr-edit-link {
  background: transparent; border: none;
  color: #7F77DD; font-size: 11px; font-weight: 500;
  font-family: inherit; cursor: pointer; padding: 0;
  display: inline-flex; align-items: center; gap: 5px;
}
.rv3-dr-edit-link svg { opacity: .85; }
.rv3-dr-edit-link:hover { text-decoration: underline; }

.rv3-dr-role-editor {
  padding-top: 2px;
}
.rv3-dr-role-foot {
  margin-top: 10px; display: flex; align-items: center; justify-content: flex-end; gap: 6px; flex-wrap: wrap;
}
.rv3-dr-role-warn {
  min-width: 220px; flex: 1; font-size: 10px; color: #A36500;
  background: rgba(239,159,39,.08); border: 1px solid rgba(239,159,39,.2); padding: 6px 8px; border-radius: 6px;
}
.rv3-dr-role-warn b { color: #7C5300; }

.rv3-dr-acc-hint {
  margin: 10px 0 4px; font-size: 10.5px; color: var(--t3, var(--t-muted));
  line-height: 1.45; font-style: italic;
}

/* Activity tab — аудит-история (структурирована по дням + детали) */
.rv3-act-count, .rv3-act-daycnt {
  font-size: 10px; font-weight: 600; color: var(--p-deep, #534AB7);
  background: rgba(124,111,247,.12); padding: 1px 7px; border-radius: 8px;
}
.rv3-act-groups { display: flex; flex-direction: column; gap: 14px; }
.rv3-act-daylbl {
  display: flex; align-items: center; gap: 8px;
  font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: .06em;
  color: var(--t3, var(--t-muted)); margin-bottom: 4px;
}
.rv3-act-list { display: flex; flex-direction: column; }
.rv3-act-item { border-bottom: 0.5px solid #F3F4F8; }
.rv3-act-item:last-child { border-bottom: none; }
.rv3-act-row {
  display: flex; gap: 10px; padding: 9px 2px; width: 100%;
  background: transparent; border: none; cursor: pointer; text-align: left; font-family: inherit;
  align-items: flex-start;
}
.rv3-act-row:hover { background: rgba(127,119,221,.04); border-radius: 7px; }
.rv3-act-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; margin-top: 5px; }
.rv3-act-body { flex: 1; min-width: 0; }
.rv3-act-top { display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; }
.rv3-act-action { font-size: 12px; font-weight: 600; }
.rv3-act-crit {
  font-size: 8.5px; font-weight: 700; text-transform: uppercase; letter-spacing: .04em;
  color: var(--sev-high, #E24B4A); background: rgba(226,75,74,.1); padding: 1px 5px; border-radius: 4px;
}
.rv3-act-entity {
  font-size: 12px; color: var(--t1, #1E2A4A);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 300px;
}
.rv3-act-meta {
  font-size: 10.5px; color: var(--t3, var(--t-muted)); margin-top: 2px;
  font-variant-numeric: tabular-nums;
}
.rv3-act-caret {
  flex-shrink: 0; color: var(--t4, #C7C9D1); margin-top: 4px;
  transition: transform .18s;
}
.rv3-act-item.open .rv3-act-caret { transform: rotate(90deg); }

.rv3-act-detail {
  margin: 0 0 10px 17px; padding: 10px 12px;
  background: var(--bg2, #FAFAFC); border: 0.5px solid var(--border-hard, #E5E7EB);
  border-radius: 9px;
}
.rv3-act-dl { display: flex; flex-direction: column; gap: 6px; }
.rv3-act-drow { display: flex; gap: 10px; font-size: 11.5px; }
.rv3-act-dk { flex-shrink: 0; width: 78px; color: var(--t3, var(--t-muted)); }
.rv3-act-dv { color: var(--t1, #1E2A4A); min-width: 0; word-break: break-word; }
.rv3-act-dv.mono, .mono { font-family: ui-monospace, 'SF Mono', Menlo, monospace; font-size: 11px; }
.rv3-act-ua { color: var(--t3, var(--t-muted)); font-size: 10.5px; }

.rv3-act-diff { margin-top: 9px; padding-top: 9px; border-top: 0.5px dashed var(--border-hard, #E5E7EB); }
.rv3-act-difflbl { font-size: 9.5px; font-weight: 600; text-transform: uppercase; letter-spacing: .06em; color: var(--t3, var(--t-muted)); margin-bottom: 5px; }
.rv3-act-diffrow { display: flex; gap: 10px; font-size: 11.5px; padding: 2px 0; }
.rv3-act-diff-f { flex-shrink: 0; width: 78px; color: var(--t2, #475569); font-weight: 500; }
.rv3-act-diff-v { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; min-width: 0; }
.rv3-act-diff-old { color: var(--sev-high, #E24B4A); text-decoration: line-through; opacity: .75; word-break: break-word; }
.rv3-act-diff-arr { color: var(--t4, #C7C9D1); }
.rv3-act-diff-new { color: var(--green, #1D9E75); font-weight: 500; word-break: break-word; }

.rv3-dr-mem-add {
  display: flex; flex-direction: column; gap: 10px;
  background: rgba(127,119,221,.06); border: 0.5px solid rgba(127,119,221,.25);
  border-radius: 8px; padding: 10px; margin-bottom: 8px;
}
.rv3-dr-mem-fields { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 8px; }
.rv3-dr-mem-fields label { min-width: 0; display: flex; flex-direction: column; gap: 5px; }
.rv3-dr-mem-fields label > span { color: var(--t3, var(--t-muted)); font-size: 9.5px; font-weight: 600; }
.rv3-dr-mem-actions { display: flex; justify-content: flex-end; gap: 6px; }
.rv3-dr-mem-sel {
  width: 100%; height: 34px; padding: 0 8px; border: 0.5px solid #D5D5DC; border-radius: 6px;
  font-size: 10.5px; background: var(--bg1, #fff); font-family: inherit; color: var(--t1, #1E2A4A);
  max-width: 100%; outline: 0;
}
.rv3-dr-mem-sel:focus { border-color: #8A82DC; box-shadow: 0 0 0 3px rgba(98,87,200,.1); }
.rv3-dr-mem-rolesel {
  width: 150px; height: 30px; padding: 0 6px; border: 0.5px solid #D5D5DC; border-radius: 5px;
  font-size: 10.5px; background: var(--bg1, #fff); font-family: inherit; color: var(--t1, #1E2A4A);
  max-width: 150px;
}
.rv3-dr-mem-x {
  background: transparent; border: none; cursor: pointer;
  color: #B0B0B0; font-size: 16px; line-height: 1;
  padding: 0 4px; border-radius: 4px;
}
.rv3-dr-mem-x:hover { color: var(--sev-high); background: rgba(226,75,74,.08); }

/* Password reset panel */
.rv3-dr-edit-link-danger { color: var(--sev-high); }
.rv3-dr-edit-link-danger:hover { text-decoration: underline; }
.rv3-dr-edit-link[disabled] { opacity: .5; cursor: not-allowed; }

.rv3-dr-pwd-panel {
  background: var(--bg2, #FAFAFC); border: 0.5px solid var(--border-hard); border-radius: 8px;
  padding: 12px;
  animation: rv3PwdIn .28s var(--ease-standard, ease) both;
}
@keyframes rv3PwdIn { from { opacity: 0; transform: translateY(-4px); } to { opacity: 1; transform: none; } }
/* Success-состояние после сброса */
.rv3-dr-pwd-panel-done {
  background: rgba(29, 158, 117, .06);
  border-color: rgba(29, 158, 117, .3);
}
.rv3-dr-pwd-success { display: flex; align-items: flex-start; gap: 9px; margin-bottom: 10px; }
.rv3-dr-pwd-success-ic {
  width: 26px; height: 26px; border-radius: 8px; flex-shrink: 0;
  background: #1D9E75; color: #fff; display: inline-flex; align-items: center; justify-content: center;
  animation: rv3PwdPop .35s cubic-bezier(.34,1.5,.5,1) both;
}
@keyframes rv3PwdPop { 0% { transform: scale(.4); opacity: 0; } 100% { transform: none; opacity: 1; } }
.rv3-dr-pwd-success-t { font-size: 12.5px; font-weight: 600; color: #0F6E56; }
.rv3-dr-pwd-success-s { font-size: 11px; color: var(--t3, #6B6880); margin-top: 2px; line-height: 1.4; }
.rv3-dr-pwd-mini-ok { background: #1D9E75 !important; color: #fff !important; border-color: #1D9E75 !important; }
.rv3-dr-pwd-hint {
  font-size: 11px; color: var(--t3, var(--t-muted)); margin-bottom: 8px; line-height: 1.45;
}
.rv3-dr-pwd-row {
  display: flex; gap: 4px; margin-bottom: 8px;
}
.rv3-dr-pwd-input {
  flex: 1; padding: 6px 10px; border: 0.5px solid #D5D5DC; border-radius: 6px;
  font-family: monospace; font-size: 12.5px; background: var(--bg1, #fff); color: var(--t1, #1E2A4A);
  letter-spacing: .02em;
}
.rv3-dr-pwd-input:focus { outline: none; border-color: #7F77DD; }
.rv3-dr-pwd-mini {
  width: 28px; height: 28px; padding: 0;
  background: var(--bg1, #fff); border: 0.5px solid #D5D5DC; border-radius: 5px;
  cursor: pointer; font-size: 13px; color: var(--t3, #5F5E5A);
  display: inline-flex; align-items: center; justify-content: center;
}
.rv3-dr-pwd-mini:hover { background: #F3F4F8; color: var(--t1, #1E2A4A); }
.rv3-dr-pwd-check {
  display: flex; align-items: center; gap: 6px;
  font-size: 11.5px; color: var(--t1, #1E2A4A); cursor: pointer;
  margin-bottom: 10px;
}
.rv3-dr-pwd-warn {
  flex: 1; font-size: 10px; color: #A36500;
  background: rgba(239,159,39,.08); padding: 5px 8px; border-radius: 5px;
}

/* Moderation flags */
.rv3-dr-mod-row {
  display: flex; align-items: center; gap: 12px;
  padding: 8px 10px; border-radius: 7px;
  border: 0.5px solid #EFEFF2; background: var(--bg2, #FAFAFC);
  margin-bottom: 6px;
}
.rv3-dr-mod-row-input { align-items: flex-start; }
.rv3-dr-mod-lbl { flex: 1; display: flex; flex-direction: column; gap: 2px; }
.rv3-dr-mod-name { font-size: 12px; color: var(--t1, #1E2A4A); font-weight: 500; }
.rv3-dr-mod-hint { font-size: 10.5px; color: var(--t3, var(--t-muted)); line-height: 1.4; }
.rv3-dr-mod-hint code {
  background: rgba(0,0,0,.04); padding: 1px 4px; border-radius: 3px;
  font-size: 10px; font-family: monospace;
}
.rv3-dr-mod-switch {
  position: relative; display: inline-block; width: 32px; height: 18px;
  cursor: pointer; flex-shrink: 0;
}
.rv3-dr-mod-switch input { opacity: 0; width: 0; height: 0; }
.rv3-dr-mod-switch input:disabled + .rv3-dr-mod-tr { opacity: .5; cursor: not-allowed; }
.rv3-dr-mod-tr {
  position: absolute; inset: 0; background: #D3D1C7;
  border-radius: 9px; transition: background .2s;
}
.rv3-dr-mod-tr::before {
  content: ""; position: absolute; top: 2px; left: 2px;
  width: 14px; height: 14px; background: var(--bg1, #fff);
  border-radius: 50%; transition: left .2s;
}
.rv3-dr-mod-switch input:checked + .rv3-dr-mod-tr { background: var(--green); }
.rv3-dr-mod-switch input:checked + .rv3-dr-mod-tr::before { left: 16px; }
.rv3-dr-mod-input-wrap { flex-shrink: 0; }
.rv3-dr-mod-input {
  padding: 5px 9px; border: 0.5px solid #D5D5DC; border-radius: 5px;
  font-size: 11.5px; font-family: inherit; background: var(--bg1, #fff);
  color: var(--t1, #1E2A4A); outline: none; min-width: 200px;
}
.rv3-dr-mod-input:focus { border-color: #7F77DD; }

/* Password admin actions */
.rv3-dr-pwd-actions { display: flex; gap: 8px; }
.rv3-status-warn { color: #D97706; font-weight: 500; }
.rv3-status-mono {
  font-family: ui-monospace, 'SF Mono', Menlo, monospace;
  font-size: 11px;
  color: var(--p-deep);
}
</style>
