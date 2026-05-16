<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import { rbacV3Api, deriveAccessMap } from '@/api/rbacV3';
import type { RbacV3UserDetail, RbacV3UserBrief } from '@/api/rbacV3';
import UserAvatar from '@/components/rbac-v3/UserAvatar.vue';
import RoleChip from '@/components/rbac-v3/RoleChip.vue';
import ModuleSelectGrid from '@/components/rbac-v3/ModuleSelectGrid.vue';
import InviteUserModal from '@/components/rbac-v3/InviteUserModal.vue';
import { createPreviewToken } from '@/api/rbacV3';

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
            <div class="rv3-dr-section-title">Роли</div>
            <div class="rv3-dr-chips">
              <RoleChip v-for="rc in detail.role_codes" :key="rc" :code="rc" />
              <span v-if="detail.role_codes.length === 0" class="rv3-empty">нет ролей</span>
            </div>
          </div>

          <div class="rv3-dr-section">
            <div class="rv3-dr-section-title">
              Членство в группах ({{ (detail.group_memberships || []).length }})
            </div>
            <div v-if="(detail.group_memberships || []).length === 0" class="rv3-empty">
              нет членства в группах — доступа к данным компаний нет
            </div>
            <div v-else class="rv3-dr-memberships">
              <div
                v-for="m in detail.group_memberships"
                :key="m.group_id"
                class="rv3-dr-mem-row"
              >
                <span class="rv3-dr-mem-grp">
                  {{ m.group_name }}
                  <span v-if="m.company_id" class="rv3-dr-mem-co-badge" title="привязана к компании">co</span>
                </span>
                <RoleChip :code="m.role_code" />
              </div>
            </div>
            <div class="rv3-dr-mem-hint">
              Добавить/убрать членство — через страницу Группы.
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
          <div class="rv3-dr-section">
            <div class="rv3-dr-section-title">Безопасность</div>
            <div class="rv3-prof-row"><span class="rv3-prof-l">Смена пароля</span><span>{{ detail.must_change_password ? 'требуется при следующем входе' : 'не требуется' }}</span></div>
            <div style="margin-top:12px;font-size:11.5px;color:#888780;">Управление MFA и сбросом пароля · Сессия 4</div>
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
</style>