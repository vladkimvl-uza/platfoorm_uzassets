<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue';
import { rbacV3Api, deriveAccessMap, rolesApi, groupsApi, adminMfaApi, generatePassword } from '@/api/rbacV3';
import type { RbacV3UserDetail, RbacV3UserBrief, RbacV3Role, RbacV3Group, AdminMfaRow } from '@/api/rbacV3';
import { moderationApi } from '@/api/moderation';
import UserAvatar from '@/components/rbac-v3/UserAvatar.vue';
import RoleChip from '@/components/rbac-v3/RoleChip.vue';
import ModuleSelectGrid from '@/components/rbac-v3/ModuleSelectGrid.vue';
import InviteUserModal from '@/components/rbac-v3/InviteUserModal.vue';
import { createPreviewToken } from '@/api/rbacV3';
import { useAuthStore } from '@/stores/auth';
import { useFormatters } from '@/composables/useFormatters';

const fmt = useFormatters();

const auth = useAuthStore();
const canManage = computed(() =>
  auth.isOwner || auth.hasPermission('admin.users'),
);

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
    error.value = e?.response?.data?.detail || 'Не удалось загрузить данные';
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
  const diff = (Date.now() - new Date(dt).getTime()) / 1000;
  if (diff < 60) return 'только что';
  if (diff < 3600) return Math.floor(diff / 60) + ' мин назад';
  if (diff < 86400) return Math.floor(diff / 3600) + ' ч назад';
  const days = Math.floor(diff / 86400);
  if (days === 1) return 'вчера';
  if (days < 30) return days + ' дн назад';
  return Math.floor(days / 30) + ' мес назад';
});

// ─── Roles + groups catalog (loaded once for the pickers) ────────
const allRoles = ref<RbacV3Role[]>([]);
const allGroups = ref<RbacV3Group[]>([]);

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

// ─── Roles editor state ──────────────────────────────────────────
const editingRoles = ref(false);
const draftRoleCodes = ref<string[]>([]);
const savingRoles = ref(false);

function openRoleEditor() {
  if (!detail.value) return;
  draftRoleCodes.value = [...detail.value.role_codes];
  editingRoles.value = true;
}

function toggleDraftRole(code: string) {
  const i = draftRoleCodes.value.indexOf(code);
  if (i >= 0) draftRoleCodes.value.splice(i, 1);
  else draftRoleCodes.value.push(code);
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
    error.value = e?.response?.data?.detail || 'Не удалось сохранить роли';
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
    error.value = e?.response?.data?.detail || 'Не удалось добавить членство';
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
    error.value = e?.response?.data?.detail || 'Не удалось сменить роль';
  }
}

async function removeMembership(groupId: string, groupName: string) {
  if (!detail.value) return;
  if (!confirm(`Убрать пользователя из группы «${groupName}»?`)) return;
  try {
    await rbacV3Api.removeMembership(detail.value.id, groupId);
    detail.value = await rbacV3Api.getUser(detail.value.id);
    emit('changed');
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 'Не удалось убрать членство';
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
watch(tab, (t) => { if (t === 'security') loadMfaStatus(); });

const forcingDisable = ref(false);
async function forceDisableMfa() {
  if (!detail.value) return;
  if (!auth.isOwner) {
    error.value = 'Только владелец платформы может принудительно отключать 2FA';
    return;
  }
  if (!confirm(
    `Принудительно отключить 2FA у ${detail.value.email}?\n\n` +
    `Будет очищено: TOTP-секрет, привязка Telegram, recovery-коды.\n` +
    `Пользователь сможет войти только по паролю. Действие записывается в Аудит.`,
  )) return;
  forcingDisable.value = true;
  try {
    await adminMfaApi.forceDisable(detail.value.id);
    await loadMfaStatus();
    emit('changed');
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 'Не удалось отключить 2FA';
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

function openPwdReset() {
  pwdValue.value = generatePassword();
  pwdMustChange.value = true;
  pwdShown.value = true;
  pwdCopied.value = false;
  showPwdReset.value = true;
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
  if (!confirm(
    `Заставить «${detail.value.full_name || detail.value.email}» сменить пароль ` +
    `при следующем защищённом запросе?\n\n` +
    `Текущий пароль будет работать только для входа (/auth/login). ` +
    `После входа доступ к любому API закрыт до смены через /change-password.`,
  )) return;
  try {
    await rbacV3Api.forcePasswordChange(detail.value.id);
    detail.value = await rbacV3Api.getUser(detail.value.id);
    emit('changed');
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 'Не удалось установить флаг';
  }
}

async function submitPwdReset() {
  if (!detail.value || !pwdValue.value) return;
  if (pwdValue.value.length < 12) {
    error.value = 'Пароль должен быть минимум 12 символов';
    return;
  }
  pwdSaving.value = true;
  try {
    await rbacV3Api.resetPassword(detail.value.id, pwdValue.value, pwdMustChange.value);
    // Refresh user (must_change_password may have flipped)
    detail.value = await rbacV3Api.getUser(detail.value.id);
    showPwdReset.value = false;
    pwdValue.value = '';
    emit('changed');
    alert(
      `Пароль сброшен. Все активные сессии этого пользователя завершены.\n` +
      `Передайте новый пароль безопасным каналом.`,
    );
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 'Не удалось сбросить пароль';
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
    error.value = e?.response?.data?.detail || 'Не удалось обновить флаг модерации';
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
    error.value = e?.response?.data?.detail || 'Не удалось сохранить организацию';
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
  if (!confirm(`Войти как ${detail.value.email}?\n\nТокен действует 30 минут. После этого вернётесь в свой аккаунт.\n\nДействие будет залогировано в Аудит.`)) return;
  impersonating.value = true;
  try {
    const resp = await createPreviewToken(detail.value.id);
    // Open new tab with preview token in URL — AppShell picks it up and stores
    const url = window.location.origin + '/?preview_token=' + encodeURIComponent(resp.access_token)
              + '&preview_email=' + encodeURIComponent(resp.target_email);
    window.open(url, '_blank');
  } catch (e: any) {
    alert(e?.response?.data?.detail || 'Не удалось получить preview-token');
  } finally {
    impersonating.value = false;
  }
}
async function onDeactivate() {
  if (!detail.value) return;
  if (!confirm(`Деактивировать пользователя ${detail.value.email}?`)) return;
  try {
    await rbacV3Api.deactivate(detail.value.id);
    emit('changed');
    emit('close');
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 'Ошибка';
  }
}
async function onDeletePermanent() {
  if (!detail.value) return;
  const input = prompt(`Это удалит пользователя НАВСЕГДА.\nВведите email для подтверждения: ${detail.value.email}`);
  if (!input || input.trim().toLowerCase() !== detail.value.email.toLowerCase()) {
    if (input !== null) alert('Email не совпадает');
    return;
  }
  try {
    await rbacV3Api.deletePermanent(detail.value.id);
    emit('changed');
    emit('close');
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 'Ошибка';
  }
}
</script>

<template>
  <div v-if="user" class="rv3-drawer">
    <div v-if="loading" class="rv3-loading">Загрузка...</div>
    <div v-else-if="error" class="rv3-error">{{ error }}</div>
    <template v-else-if="detail">
      <!-- Header -->
      <div class="rv3-dr-head">
        <div class="rv3-dr-head-top">
          <UserAvatar :email="detail.email" :full-name="detail.full_name" :size="48" />
          <div style="flex:1;min-width:0;">
            <div class="rv3-dr-name">{{ detail.full_name }}</div>
            <div class="rv3-dr-meta">
              {{ detail.email }} · последний вход {{ lastLoginRelative }}
            </div>
          </div>
          <button class="rv3-dr-close" @click="emit('close')" aria-label="close">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>
        <div class="rv3-dr-tabs">
          <button :class="['rv3-dr-tab', { on: tab === 'access' }]" @click="tab = 'access'">Доступ</button>
          <button :class="['rv3-dr-tab', { on: tab === 'profile' }]" @click="tab = 'profile'">Профиль</button>
          <button :class="['rv3-dr-tab', { on: tab === 'activity' }]" @click="tab = 'activity'">Активность</button>
          <button :class="['rv3-dr-tab', { on: tab === 'security' }]" @click="tab = 'security'">Безопасность</button>
        </div>
      </div>

      <div class="rv3-dr-body">
        <!-- ACCESS TAB -->
        <div v-if="tab === 'access'">
          <div class="rv3-dr-section">
            <div class="rv3-dr-section-title rv3-dr-section-title-row">
              <span>Системные роли</span>
              <button
                v-if="canManage && !detail.is_owner && !editingRoles"
                class="rv3-dr-edit-link"
                @click="openRoleEditor"
              >Изменить</button>
            </div>
            <!-- Read-only chips -->
            <div v-if="!editingRoles" class="rv3-dr-chips">
              <RoleChip v-for="rc in detail.role_codes" :key="rc" :code="rc" />
              <span v-if="detail.role_codes.length === 0" class="rv3-empty">нет ролей</span>
            </div>
            <!-- Editor -->
            <div v-else class="rv3-dr-role-editor">
              <div class="rv3-dr-role-grid">
                <label
                  v-for="r in allRoles"
                  :key="r.code"
                  class="rv3-dr-role-opt"
                  :class="{ on: draftRoleCodes.includes(r.code) }"
                >
                  <input
                    type="checkbox"
                    :checked="draftRoleCodes.includes(r.code)"
                    @change="toggleDraftRole(r.code)"
                  />
                  <span class="rv3-dr-role-opt-name">{{ r.name_ru }}</span>
                  <code class="rv3-dr-role-opt-code">{{ r.code }}</code>
                </label>
              </div>
              <div class="rv3-dr-role-foot">
                <span class="rv3-dr-role-warn" v-if="draftRoleCodes.includes('admin')">
                  ⚠ Роль <b>admin</b> обходит все scope-проверки — пользователь будет видеть все компании.
                </span>
                <button class="rv3-btn rv3-btn-ghost" @click="editingRoles = false" :disabled="savingRoles">Отмена</button>
                <button class="rv3-btn rv3-btn-purple" @click="saveRoles" :disabled="savingRoles">
                  {{ savingRoles ? 'Сохранение…' : 'Сохранить роли' }}
                </button>
              </div>
            </div>
          </div>

          <div class="rv3-dr-section">
            <div class="rv3-dr-section-title rv3-dr-section-title-row">
              <span>Членство в группах ({{ (detail.group_memberships || []).length }})</span>
              <button
                v-if="canManage && !detail.is_owner && !showAddMembership && availableGroupsForAdd.length"
                class="rv3-dr-edit-link"
                @click="showAddMembership = true"
              >+ Добавить</button>
            </div>

            <!-- Add-membership inline form -->
            <div v-if="showAddMembership" class="rv3-dr-mem-add">
              <select v-model="draftAddGroupId" class="rv3-dr-mem-sel">
                <option value="">— выбрать группу —</option>
                <option v-for="g in availableGroupsForAdd" :key="g.id" :value="g.id">
                  {{ g.name }}{{ g.company_id ? ' · co' : '' }}
                </option>
              </select>
              <select v-model="draftAddRoleCode" class="rv3-dr-mem-sel">
                <option v-for="r in allRoles" :key="r.code" :value="r.code">{{ r.name_ru }}</option>
              </select>
              <button class="rv3-btn rv3-btn-ghost" @click="showAddMembership = false" :disabled="savingMembership">Отмена</button>
              <button class="rv3-btn rv3-btn-purple" @click="addMembership"
                      :disabled="!draftAddGroupId || savingMembership">
                {{ savingMembership ? '…' : 'Добавить' }}
              </button>
            </div>

            <div v-if="(detail.group_memberships || []).length === 0 && !showAddMembership" class="rv3-empty">
              нет членства в группах — доступа к данным компаний нет
            </div>
            <div v-else-if="(detail.group_memberships || []).length" class="rv3-dr-memberships">
              <div
                v-for="m in detail.group_memberships"
                :key="m.group_id"
                class="rv3-dr-mem-row"
              >
                <span class="rv3-dr-mem-grp">
                  {{ m.group_name }}
                  <span v-if="m.company_id" class="rv3-dr-mem-co-badge" title="привязана к компании">co</span>
                </span>
                <select
                  v-if="canManage && !detail.is_owner"
                  :value="m.role_code"
                  class="rv3-dr-mem-rolesel"
                  @change="changeMembershipRole(m.group_id, ($event.target as HTMLSelectElement).value)"
                  title="Сменить роль в этой группе"
                >
                  <option v-for="r in allRoles" :key="r.code" :value="r.code">{{ r.name_ru }}</option>
                </select>
                <RoleChip v-else :code="m.role_code" />
                <button
                  v-if="canManage && !detail.is_owner"
                  class="rv3-dr-mem-x"
                  @click="removeMembership(m.group_id, m.group_name)"
                  title="Убрать из группы"
                >×</button>
              </div>
            </div>
            <div v-if="!canManage" class="rv3-dr-mem-hint">
              Для редактирования членства нужны права admin.users.
            </div>
          </div>

          <div class="rv3-dr-section">
            <div class="rv3-dr-section-title rv3-dr-section-title-row">
              <span>Доступ к модулям · {{ accessCount }} из 16</span>
            </div>
            <ModuleSelectGrid
              :model-value="access.levels"
              :sources="access.sources"
              :columns="2"
            />
            <div class="rv3-legend">
              <span><span class="rv3-sw" style="background:#1D9E75"></span>admin</span>
              <span><span class="rv3-sw" style="background:#7F77DD"></span>write</span>
              <span><span class="rv3-sw" style="background:#378ADD"></span>read</span>
              <span><span class="rv3-sw" style="background:#D1D5DB"></span>нет доступа</span>
            </div>
          </div>
        </div>

        <!-- PROFILE TAB -->
        <div v-else-if="tab === 'profile'">
          <div class="rv3-dr-section">
            <div class="rv3-dr-section-title">Профиль</div>
            <div class="rv3-prof-row"><span class="rv3-prof-l">ФИО</span><span>{{ detail.full_name }}</span></div>
            <div class="rv3-prof-row"><span class="rv3-prof-l">Email</span><span>{{ detail.email }}</span></div>
            <div class="rv3-prof-row"><span class="rv3-prof-l">Отдел</span><span>{{ detail.department || '—' }}</span></div>
            <div class="rv3-prof-row"><span class="rv3-prof-l">Создан</span><span>{{ new Date(detail.created_at).toLocaleDateString('ru-RU') }}</span></div>
            <div class="rv3-prof-row"><span class="rv3-prof-l">Статус</span><span :style="{ color: detail.is_active ? '#1D9E75' : '#E24B4A' }">{{ detail.is_active ? 'активен' : 'заблокирован' }}</span></div>
            <div class="rv3-prof-row" v-if="detail.is_owner"><span class="rv3-prof-l">Особое</span><span style="color:#B27015;font-weight:500;">владелец платформы</span></div>
          </div>
        </div>

        <!-- ACTIVITY TAB -->
        <div v-else-if="tab === 'activity'">
          <div class="rv3-dr-section">
            <div class="rv3-dr-section-title">Последняя активность</div>
            <div class="rv3-empty">История логинов и действий будет показана здесь · Сессия 4</div>
          </div>
        </div>

        <!-- SECURITY TAB -->
        <div v-else-if="tab === 'security'">

          <!-- ── Password ── -->
          <div class="rv3-dr-section">
            <div class="rv3-dr-section-title rv3-dr-section-title-row">
              <span>Пароль</span>
              <div v-if="canManage && !detail.is_owner && !showPwdReset" class="rv3-dr-pwd-actions">
                <button
                  v-if="!detail.must_change_password"
                  class="rv3-dr-edit-link"
                  @click="submitForceChange"
                  title="Установить флаг must_change_password=true без смены пароля"
                >🔒 Заставить сменить</button>
                <button class="rv3-dr-edit-link" @click="openPwdReset">🔑 Сбросить</button>
              </div>
            </div>
            <div v-if="!showPwdReset" class="rv3-prof-row">
              <span class="rv3-prof-l">Статус</span>
              <span :class="{ 'rv3-status-warn': detail.must_change_password }">
                {{ detail.must_change_password ? '⚠ требуется смена при следующем входе' : '✓ действителен' }}
              </span>
            </div>
            <div v-if="!showPwdReset && (detail as any).password_changed_at" class="rv3-prof-row">
              <span class="rv3-prof-l">Последняя смена</span>
              <span class="rv3-status-mono">{{ new Date((detail as any).password_changed_at).toLocaleString('ru-RU') }}</span>
            </div>

            <div v-else class="rv3-dr-pwd-panel">
              <div class="rv3-dr-pwd-hint">
                Сгенерирован новый пароль. После сохранения он применяется немедленно
                и все живые сессии этого пользователя будут завершены.
              </div>
              <div class="rv3-dr-pwd-row">
                <input
                  :type="pwdShown ? 'text' : 'password'"
                  v-model="pwdValue"
                  class="rv3-dr-pwd-input"
                  autocomplete="off"
                />
                <button class="rv3-dr-pwd-mini" @click="pwdShown = !pwdShown" :title="pwdShown ? 'Скрыть' : 'Показать'">
                  {{ pwdShown ? '🙈' : '👁' }}
                </button>
                <button class="rv3-dr-pwd-mini" @click="pwdValue = generatePassword()" title="Сгенерировать новый">↻</button>
                <button class="rv3-dr-pwd-mini" @click="copyPwd" :title="pwdCopied ? 'Скопировано' : 'Скопировать'">
                  {{ pwdCopied ? '✓' : '⧉' }}
                </button>
              </div>
              <label class="rv3-dr-pwd-check">
                <input type="checkbox" v-model="pwdMustChange"/>
                Требовать смену пароля при следующем входе
              </label>
              <div class="rv3-dr-role-foot">
                <span class="rv3-dr-pwd-warn">⚠ Передайте новый пароль безопасным каналом (не в email).</span>
                <button class="rv3-btn rv3-btn-ghost" @click="showPwdReset = false" :disabled="pwdSaving">Отмена</button>
                <button class="rv3-btn rv3-btn-purple" @click="submitPwdReset"
                        :disabled="pwdSaving || !pwdValue || pwdValue.length < 12">
                  {{ pwdSaving ? 'Сохранение…' : 'Сбросить пароль' }}
                </button>
              </div>
            </div>
          </div>

          <!-- ── MFA ── -->
          <div class="rv3-dr-section">
            <div class="rv3-dr-section-title rv3-dr-section-title-row">
              <span>Двухфакторная аутентификация</span>
              <button
                v-if="auth.isOwner && !detail.is_owner && mfaRow?.mfa_enabled"
                class="rv3-dr-edit-link rv3-dr-edit-link-danger"
                @click="forceDisableMfa"
                :disabled="forcingDisable"
              >{{ forcingDisable ? '…' : 'Сбросить 2FA' }}</button>
            </div>

            <div v-if="mfaLoading" class="rv3-empty">Загрузка статуса…</div>
            <div v-else-if="!mfaRow" class="rv3-empty">статус не доступен</div>
            <div v-else>
              <div class="rv3-prof-row">
                <span class="rv3-prof-l">MFA</span>
                <span :style="{ color: mfaRow.mfa_enabled ? '#1D9E75' : '#E24B4A' }">
                  {{ mfaRow.mfa_enabled ? 'включена' : 'отключена' }}
                  <span v-if="mfaRow.mfa_enabled" style="color:#888780">· {{ mfaRow.mfa_method }}</span>
                </span>
              </div>
              <div class="rv3-prof-row">
                <span class="rv3-prof-l">Telegram</span>
                <span>
                  <template v-if="mfaRow.telegram_linked">
                    @{{ mfaRow.telegram_username || '—' }}
                    <span style="color:#888780" v-if="mfaRow.telegram_linked_at">
                      · с {{ new Date(mfaRow.telegram_linked_at).toLocaleDateString('ru-RU') }}
                    </span>
                  </template>
                  <span v-else style="color:#888780">не привязан</span>
                </span>
              </div>
              <div class="rv3-prof-row">
                <span class="rv3-prof-l">Recovery-коды</span>
                <span :style="{ color: mfaRow.recovery_codes_remaining > 2 ? '#1D9E75' : (mfaRow.recovery_codes_remaining > 0 ? '#EF9F27' : '#E24B4A') }">
                  {{ mfaRow.recovery_codes_remaining }} осталось
                </span>
              </div>
              <div class="rv3-prof-row" v-if="mfaRow.last_login_at">
                <span class="rv3-prof-l">Последний вход</span>
                <span>
                  {{ fmt.fmtDateTime(mfaRow.last_login_at) }}
                  <span v-if="mfaRow.last_login_ip" style="color:#888780">· {{ mfaRow.last_login_ip }}</span>
                </span>
              </div>

              <div v-if="!auth.isOwner && mfaRow.mfa_enabled" class="rv3-dr-mem-hint">
                Сбросить 2FA пользователя может только владелец платформы.
              </div>
              <div v-if="!mfaRow.mfa_enabled" class="rv3-dr-mem-hint">
                Пользователь не настроил 2FA. Сам пользователь делает это в Настройках профиля.
              </div>
            </div>
          </div>

          <!-- ── Moderation flags (Pack 148-followup) ── -->
          <div class="rv3-dr-section">
            <div class="rv3-dr-section-title">Модерация</div>
            <div v-if="!canManage" class="rv3-dr-mem-hint">
              Управление флагами модерации требует право admin.users.
            </div>
            <div v-else-if="detail.is_owner" class="rv3-dr-mem-hint">
              Владелец платформы всегда обходит модерацию.
            </div>
            <div v-else>
              <div class="rv3-dr-mod-row">
                <span class="rv3-dr-mod-lbl">
                  <span class="rv3-dr-mod-name">External (внешний пользователь)</span>
                  <span class="rv3-dr-mod-hint">
                    Включает матчинг по правилам с <code>trigger_is_external=true</code>.
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
                  <span class="rv3-dr-mod-name">Bypass moderation (обход)</span>
                  <span class="rv3-dr-mod-hint">
                    Запись идёт напрямую, даже если правило матчится.
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
                  <span class="rv3-dr-mod-name">Организация</span>
                  <span class="rv3-dr-mod-hint">Видна в списке «Подмодерируемые».</span>
                </span>
                <div class="rv3-dr-mod-input-wrap">
                  <input
                    v-model="modOrgDraft"
                    class="rv3-dr-mod-input"
                    placeholder="напр. АО Контрагент"
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
        <button class="rv3-btn rv3-btn-purple" @click="showClone = true">Создать аналогичного</button>
        <button
          v-if="detail.is_active && !detail.role_codes.includes('admin') && !detail.role_codes.includes('ceo')"
          class="rv3-btn rv3-btn-ghost rv3-btn-imp"
          @click="startImpersonate"
          :disabled="impersonating"
          title="Открыть платформу глазами этого пользователя (30 мин)"
        >
          <svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><circle cx="8" cy="5" r="2.5"/><path d="M3 13c0-2.5 2-4 5-4s5 1.5 5 4"/></svg>
          {{ impersonating ? 'Загрузка...' : 'Войти как' }}
        </button>
        <div style="flex:1;"></div>
        <button class="rv3-btn rv3-btn-ghost" @click="onDeactivate" v-if="detail.is_active">Деактивировать</button>
        <button class="rv3-btn rv3-btn-red" @click="onDeletePermanent">Удалить</button>
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
  background: #fff;
  display: flex;
  flex-direction: column;
  height: 100%;
  border-left: 0.5px solid #E5E7EB;
}
.rv3-loading, .rv3-error {
  padding: 40px;
  text-align: center;
  color: #888780;
  font-size: 13px;
}
.rv3-error { color: #E24B4A; }

.rv3-dr-head { padding: 18px 22px 0; border-bottom: 0.5px solid #E5E7EB; }
.rv3-dr-head-top { display: flex; align-items: center; gap: 14px; margin-bottom: 14px; }
.rv3-dr-name { font-size: 16px; font-weight: 500; letter-spacing: -.01em; }
.rv3-dr-meta { font-size: 11px; color: #888780; margin-top: 3px; }
.rv3-dr-close {
  width: 30px; height: 30px;
  background: transparent; border: none; cursor: pointer;
  color: #888780; border-radius: 6px;
  display: flex; align-items: center; justify-content: center;
}
.rv3-dr-close:hover { background: #F3F4F8; color: #1E2A4A; }

.rv3-dr-tabs { display: flex; gap: 0; }
.rv3-dr-tab {
  padding: 9px 14px;
  font-size: 12px; font-weight: 500;
  color: #888780;
  background: transparent; border: none; border-bottom: 2px solid transparent;
  cursor: pointer; font-family: inherit;
}
.rv3-dr-tab:hover { color: #1E2A4A; }
.rv3-dr-tab.on { color: #1E2A4A; border-bottom-color: #7F77DD; }

.rv3-dr-body { flex: 1; overflow-y: auto; padding: 18px 22px; }

.rv3-dr-section { margin-bottom: 18px; }
.rv3-dr-section-title {
  font-size: 10px; font-weight: 500; color: #888780;
  letter-spacing: .06em; text-transform: uppercase;
  margin-bottom: 8px;
}
.rv3-dr-section-title-row {
  display: flex; align-items: center; justify-content: space-between;
}
.rv3-dr-chips { display: flex; gap: 6px; flex-wrap: wrap; }
.rv3-dr-scope {
  background: #FAFAFC; border: 0.5px solid #E5E7EB; border-radius: 8px;
  padding: 10px 12px; font-size: 11.5px; color: #1E2A4A;
}
.rv3-empty {
  font-size: 11.5px; color: #888780;
  font-style: italic;
}
.rv3-dr-memberships {
  display: flex; flex-direction: column; gap: 4px;
  background: #FAFAFC; border: 0.5px solid #E5E7EB; border-radius: 8px;
  padding: 8px 10px;
}
.rv3-dr-mem-row {
  display: flex; align-items: center; gap: 10px;
  padding: 4px 0; font-size: 12px; color: #1E2A4A;
}
.rv3-dr-mem-row:not(:last-child) {
  border-bottom: 0.5px solid #F0F0F4;
}
.rv3-dr-mem-grp {
  flex: 1; display: flex; align-items: center; gap: 6px;
}
.rv3-dr-mem-co-badge {
  font-size: 8.5px; color: #1D9E75;
  background: rgba(29,158,117,.1);
  padding: 1px 5px; border-radius: 3px;
  font-weight: 500; letter-spacing: .04em; text-transform: uppercase;
}
.rv3-dr-mem-hint {
  margin-top: 6px; font-size: 10.5px; color: #888780;
  font-style: italic;
}
.rv3-legend {
  margin-top: 12px;
  display: flex; gap: 14px; flex-wrap: wrap;
  font-size: 9.5px; color: #888780;
}
.rv3-legend span { display: flex; align-items: center; gap: 5px; }
.rv3-sw { width: 8px; height: 8px; border-radius: 2px; }
.rv3-prof-row {
  display: flex; gap: 12px; padding: 6px 0;
  font-size: 12px; border-bottom: 0.5px solid #F3F4F8;
}
.rv3-prof-l { color: #888780; width: 110px; flex-shrink: 0; }

.rv3-dr-foot {
  padding: 14px 22px;
  background: #FAFAFC;
  border-top: 0.5px solid #E5E7EB;
  display: flex; gap: 8px; align-items: center;
}
.rv3-btn {
  padding: 7px 12px; border-radius: 8px;
  font-size: 11px; font-weight: 500; font-family: inherit;
  cursor: pointer;
}
.rv3-btn-purple {
  background: #534AB7; border: none; color: #fff;
}
.rv3-btn-purple:hover { background: #463E9F; }
.rv3-btn-ghost {
  background: transparent; border: 1px solid #E5E7EB; color: #1E2A4A;
}
.rv3-btn-ghost:hover { background: #F3F4F8; }
.rv3-btn-red {
  background: #fff; border: 1px solid #E24B4A; color: #E24B4A;
}
.rv3-btn-red:hover { background: rgba(226,75,74,.06); }
.rv3-btn-imp {
  display: flex; align-items: center; gap: 5px;
  color: #534AB7 !important; border-color: rgba(127,119,221,.4) !important;
}
.rv3-btn-imp:hover { background: rgba(127,119,221,.06); }
.rv3-btn-imp:disabled { opacity: .55; cursor: not-allowed; }

/* Pack 148-followup: in-place role + membership editor */
.rv3-dr-edit-link {
  background: transparent; border: none;
  color: #7F77DD; font-size: 11px; font-weight: 500;
  font-family: inherit; cursor: pointer; padding: 0;
}
.rv3-dr-edit-link:hover { text-decoration: underline; }

.rv3-dr-role-editor {
  background: #FAFAFC; border: 0.5px solid #E5E7EB; border-radius: 8px;
  padding: 10px;
}
.rv3-dr-role-grid {
  display: grid; grid-template-columns: 1fr 1fr; gap: 4px;
}
.rv3-dr-role-opt {
  display: flex; align-items: center; gap: 6px;
  padding: 5px 8px; border-radius: 5px;
  font-size: 11.5px; color: #1E2A4A; cursor: pointer;
  transition: background .12s;
}
.rv3-dr-role-opt:hover { background: rgba(127,119,221,.06); }
.rv3-dr-role-opt.on { background: rgba(127,119,221,.12); }
.rv3-dr-role-opt input { margin: 0; }
.rv3-dr-role-opt-name { flex: 1; }
.rv3-dr-role-opt-code { font-family: monospace; font-size: 10px; color: #888780; }
.rv3-dr-role-foot {
  margin-top: 10px; display: flex; align-items: center; gap: 6px;
}
.rv3-dr-role-warn {
  flex: 1; font-size: 10px; color: #A36500;
  background: rgba(239,159,39,.08); padding: 5px 8px; border-radius: 5px;
}
.rv3-dr-role-warn b { color: #7C5300; }

.rv3-dr-mem-add {
  display: grid; grid-template-columns: 1fr 1fr auto auto; gap: 5px;
  background: rgba(127,119,221,.06); border: 0.5px solid rgba(127,119,221,.25);
  border-radius: 8px; padding: 8px; margin-bottom: 8px;
}
.rv3-dr-mem-sel {
  padding: 5px 8px; border: 0.5px solid #D5D5DC; border-radius: 5px;
  font-size: 11.5px; background: #fff; font-family: inherit; color: #1E2A4A;
}
.rv3-dr-mem-rolesel {
  padding: 3px 6px; border: 0.5px solid #D5D5DC; border-radius: 5px;
  font-size: 11px; background: #fff; font-family: inherit; color: #1E2A4A;
  max-width: 130px;
}
.rv3-dr-mem-x {
  background: transparent; border: none; cursor: pointer;
  color: #B0B0B0; font-size: 16px; line-height: 1;
  padding: 0 4px; border-radius: 4px;
}
.rv3-dr-mem-x:hover { color: #E24B4A; background: rgba(226,75,74,.08); }

/* Password reset panel */
.rv3-dr-edit-link-danger { color: #E24B4A; }
.rv3-dr-edit-link-danger:hover { text-decoration: underline; }
.rv3-dr-edit-link[disabled] { opacity: .5; cursor: not-allowed; }

.rv3-dr-pwd-panel {
  background: #FAFAFC; border: 0.5px solid #E5E7EB; border-radius: 8px;
  padding: 12px;
}
.rv3-dr-pwd-hint {
  font-size: 11px; color: #888780; margin-bottom: 8px; line-height: 1.45;
}
.rv3-dr-pwd-row {
  display: flex; gap: 4px; margin-bottom: 8px;
}
.rv3-dr-pwd-input {
  flex: 1; padding: 6px 10px; border: 0.5px solid #D5D5DC; border-radius: 6px;
  font-family: monospace; font-size: 12.5px; background: #fff; color: #1E2A4A;
  letter-spacing: .02em;
}
.rv3-dr-pwd-input:focus { outline: none; border-color: #7F77DD; }
.rv3-dr-pwd-mini {
  width: 28px; height: 28px; padding: 0;
  background: #fff; border: 0.5px solid #D5D5DC; border-radius: 5px;
  cursor: pointer; font-size: 13px; color: #5F5E5A;
  display: inline-flex; align-items: center; justify-content: center;
}
.rv3-dr-pwd-mini:hover { background: #F3F4F8; color: #1E2A4A; }
.rv3-dr-pwd-check {
  display: flex; align-items: center; gap: 6px;
  font-size: 11.5px; color: #1E2A4A; cursor: pointer;
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
  border: 0.5px solid #EFEFF2; background: #FAFAFC;
  margin-bottom: 6px;
}
.rv3-dr-mod-row-input { align-items: flex-start; }
.rv3-dr-mod-lbl { flex: 1; display: flex; flex-direction: column; gap: 2px; }
.rv3-dr-mod-name { font-size: 12px; color: #1E2A4A; font-weight: 500; }
.rv3-dr-mod-hint { font-size: 10.5px; color: #888780; line-height: 1.4; }
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
  width: 14px; height: 14px; background: #fff;
  border-radius: 50%; transition: left .2s;
}
.rv3-dr-mod-switch input:checked + .rv3-dr-mod-tr { background: #1D9E75; }
.rv3-dr-mod-switch input:checked + .rv3-dr-mod-tr::before { left: 16px; }
.rv3-dr-mod-input-wrap { flex-shrink: 0; }
.rv3-dr-mod-input {
  padding: 5px 9px; border: 0.5px solid #D5D5DC; border-radius: 5px;
  font-size: 11.5px; font-family: inherit; background: #fff;
  color: #1E2A4A; outline: none; min-width: 200px;
}
.rv3-dr-mod-input:focus { border-color: #7F77DD; }

/* Password admin actions */
.rv3-dr-pwd-actions { display: flex; gap: 8px; }
.rv3-status-warn { color: #D97706; font-weight: 500; }
.rv3-status-mono {
  font-family: ui-monospace, 'SF Mono', Menlo, monospace;
  font-size: 11px;
  color: #534AB7;
}
</style>