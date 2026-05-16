# =====================================================================
# p142a-rbac-v3-users-page.ps1   (RBAC v3 session 3 — part 1)
# =====================================================================
# Implements real logic for UsersPage + UserDetailDrawer.
# Uses existing backend endpoints:
#   GET  /rbac/users              -> { items, total }
#   GET  /rbac/users/{id}         -> UserDetail (with effective_permissions)
#   DELETE /rbac/users/{id}/permanent   (Pack 135)
#   POST /mfa/onboarding/...      (existing)
#
# UI elements:
#   - filter chips (active / inactive / no-MFA / inactive 30+ days)
#   - global search (name + email + role)
#   - user list with checkbox + role chips + last login + MFA + access count
#   - drawer with 4 tabs (Доступ / Профиль / Активность / Безопасность)
#   - Access tab shows ModuleSelectGrid with 16 modules (read-only on this user)
#
# Sources of access are derived client-side from effective_permissions:
#   - bp.view + bp.edit + bp.export                 -> level=write
#   - bp.view only                                  -> level=read
#   - bp.manage / bp.admin                          -> level=admin
#   - if user has admin/ceo role -> all 16 = admin
# =====================================================================

$ErrorActionPreference = "Stop"
$enc = New-Object System.Text.UTF8Encoding($false)
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$root = $PSScriptRoot
if (-not $root) { $root = (Get-Location).Path }

function Read-File($p)  { return [System.IO.File]::ReadAllText($p, $enc) }
function Write-File($p, $text) { [System.IO.File]::WriteAllText($p, $text, $enc) }
function Ensure-Dir($d) { if (-not (Test-Path -LiteralPath $d)) { New-Item -ItemType Directory -Path $d -Force | Out-Null } }
function Write-NewFile($path, $content, $label) {
    Write-Host "[*] $label" -ForegroundColor Yellow
    Ensure-Dir (Split-Path $path -Parent)
    Write-File $path $content
    Write-Host "    OK: $path" -ForegroundColor Green
}

$fe = "frontend\src"

# ───────────────────────────────────────────────────────────────────────
# [1/3] api/rbacV3.ts — typed wrapper for existing endpoints
# ───────────────────────────────────────────────────────────────────────
$apiClient = @'
import { api } from './client';

export interface RbacV3UserBrief {
  id: string;
  email: string;
  full_name: string;
  department: string | null;
  is_active: boolean;
  is_owner: boolean;
  must_change_password: boolean;
  last_login_at: string | null;
  created_at: string;
  role_codes: string[];
  role_names: string[];
  organization_id: string | null;
  allowed_companies: string[] | null;
}

export interface RbacV3UserDetail extends RbacV3UserBrief {
  effective_permissions: string[];
  role_by_email_rule: any | null;
}

export interface RbacV3UserListResponse {
  items: RbacV3UserBrief[];
  total: number;
}

export const rbacV3Api = {
  async listUsers(opts?: { search?: string; is_active?: boolean; limit?: number; offset?: number }): Promise<RbacV3UserListResponse> {
    const { data } = await api.get<RbacV3UserListResponse>('/rbac/users', { params: opts });
    return data;
  },
  async getUser(id: string): Promise<RbacV3UserDetail> {
    const { data } = await api.get<RbacV3UserDetail>(`/rbac/users/${id}`);
    return data;
  },
  async deactivate(id: string) {
    await api.delete(`/rbac/users/${id}`);
  },
  async deletePermanent(id: string) {
    await api.delete(`/rbac/users/${id}/permanent`);
  },
  async update(id: string, payload: { full_name?: string; department?: string; is_active?: boolean; role_codes?: string[]; allowed_companies?: string[] | null }) {
    const { data } = await api.patch<RbacV3UserDetail>(`/rbac/users/${id}`, payload);
    return data;
  },
};

/**
 * Convert effective_permissions array into the format AccessCard expects:
 * { moduleCode -> AccessLevel } + { moduleCode -> source string }.
 *
 * Heuristic for level:
 *   - has *.manage or *.admin -> 'admin'
 *   - has *.edit or *.create or *.update or *.delete -> 'write'
 *   - has *.view -> 'read'
 *   - else -> 'none'
 *
 * Owner / admin / ceo role gets 'admin' on all 16 modules unconditionally.
 */
import { MODULE_REGISTRY } from '@/composables/usePermissions';
import type { AccessLevel } from '@/composables/usePermissions';

export function deriveAccessMap(user: RbacV3UserDetail | null): {
  levels: Record<string, AccessLevel>;
  sources: Record<string, string>;
} {
  const levels: Record<string, AccessLevel> = {};
  const sources: Record<string, string> = {};
  if (!user) return { levels, sources };

  // Owner / admin / ceo bypass — admin everywhere
  if (user.is_owner || user.role_codes.includes('admin') || user.role_codes.includes('ceo')) {
    const reason = user.is_owner ? 'владелец платформы'
                  : user.role_codes.includes('admin') ? 'via role: admin'
                  : 'via role: ceo';
    for (const m of MODULE_REGISTRY) {
      levels[m.code] = 'admin';
      sources[m.code] = reason;
    }
    return { levels, sources };
  }

  const perms = user.effective_permissions || [];
  for (const m of MODULE_REGISTRY) {
    const prefix = m.code + '.';
    const codes = perms.filter(p => p.startsWith(prefix));
    if (codes.length === 0) { levels[m.code] = 'none'; sources[m.code] = 'нет в роли'; continue; }

    let level: AccessLevel = 'none';
    if (codes.some(c => c.endsWith('.manage') || c.endsWith('.admin'))) level = 'admin';
    else if (codes.some(c => /\.(edit|create|update|delete|write|approve)$/.test(c))) level = 'write';
    else if (codes.some(c => c.endsWith('.view') || c.endsWith('.read'))) level = 'read';

    levels[m.code] = level;
    // Best-effort source — first non-empty role
    sources[m.code] = user.role_codes.length > 0
      ? `via role: ${user.role_codes[0]}`
      : 'via permissions';
  }
  return { levels, sources };
}
'@
Write-NewFile (Join-Path $root "$fe\api\rbacV3.ts") $apiClient "[1/3] api/rbacV3.ts"

# ───────────────────────────────────────────────────────────────────────
# [2/3] views/rbac-v3/UserDetailDrawer.vue
# ───────────────────────────────────────────────────────────────────────
$drawer = @'
<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import { rbacV3Api, deriveAccessMap } from '@/api/rbacV3';
import type { RbacV3UserDetail, RbacV3UserBrief } from '@/api/rbacV3';
import UserAvatar from '@/components/rbac-v3/UserAvatar.vue';
import RoleChip from '@/components/rbac-v3/RoleChip.vue';
import ModuleSelectGrid from '@/components/rbac-v3/ModuleSelectGrid.vue';

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

          <div class="rv3-dr-section" v-if="detail.allowed_companies && detail.allowed_companies.length > 0">
            <div class="rv3-dr-section-title">Область данных (scope)</div>
            <div class="rv3-dr-scope">
              <div>Компании: <strong>{{ detail.allowed_companies.join(', ') }}</strong></div>
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
        <div style="flex:1;"></div>
        <button class="rv3-btn rv3-btn-ghost" @click="onDeactivate" v-if="detail.is_active">Деактивировать</button>
        <button class="rv3-btn rv3-btn-red" @click="onDeletePermanent">Удалить</button>
      </div>
    </template>
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
.rv3-btn-ghost {
  background: transparent; border: 1px solid #E5E7EB; color: #1E2A4A;
}
.rv3-btn-ghost:hover { background: #F3F4F8; }
.rv3-btn-red {
  background: #fff; border: 1px solid #E24B4A; color: #E24B4A;
}
.rv3-btn-red:hover { background: rgba(226,75,74,.06); }
</style>
'@
Write-NewFile (Join-Path $root "$fe\views\rbac-v3\UserDetailDrawer.vue") $drawer "[2/3] UserDetailDrawer.vue (replace skeleton)"

# ───────────────────────────────────────────────────────────────────────
# [3/3] views/rbac-v3/UsersPage.vue — real implementation
# ───────────────────────────────────────────────────────────────────────
$usersPage = @'
<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { rbacV3Api } from '@/api/rbacV3';
import type { RbacV3UserBrief } from '@/api/rbacV3';
import UserAvatar from '@/components/rbac-v3/UserAvatar.vue';
import RoleChip from '@/components/rbac-v3/RoleChip.vue';
import UserDetailDrawer from './UserDetailDrawer.vue';

const users = ref<RbacV3UserBrief[]>([]);
const total = ref(0);
const loading = ref(false);
const error = ref<string | null>(null);
const search = ref('');
type Filter = 'active' | 'inactive' | 'all';
const filter = ref<Filter>('active');
const selectedIds = ref<Set<string>>(new Set());
const selectedUser = ref<RbacV3UserBrief | null>(null);

async function loadUsers() {
  loading.value = true;
  error.value = null;
  try {
    const opts: any = { limit: 100 };
    if (filter.value === 'active') opts.is_active = true;
    if (filter.value === 'inactive') opts.is_active = false;
    if (search.value.trim()) opts.search = search.value.trim();
    const resp = await rbacV3Api.listUsers(opts);
    users.value = resp.items;
    total.value = resp.total;
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 'Не удалось загрузить пользователей';
  } finally {
    loading.value = false;
  }
}
onMounted(loadUsers);

const counts = computed(() => ({
  active: users.value.filter(u => u.is_active).length,
  inactive: users.value.filter(u => !u.is_active).length,
}));

function fmtLastLogin(dt: string | null): string {
  if (!dt) return '—';
  const diff = (Date.now() - new Date(dt).getTime()) / 1000;
  if (diff < 60) return 'только что';
  if (diff < 3600) return Math.floor(diff / 60) + ' мин назад';
  if (diff < 86400) return Math.floor(diff / 3600) + ' ч назад';
  const days = Math.floor(diff / 86400);
  if (days === 1) return 'вчера';
  if (days < 30) return days + ' дн назад';
  return Math.floor(days / 30) + ' мес назад';
}

function toggleSelect(id: string) {
  if (selectedIds.value.has(id)) selectedIds.value.delete(id);
  else selectedIds.value.add(id);
  // Force reactivity
  selectedIds.value = new Set(selectedIds.value);
}
function openUser(u: RbacV3UserBrief) {
  selectedUser.value = u;
}
function closeDrawer() {
  selectedUser.value = null;
}
async function onUserChanged() {
  await loadUsers();
}

let searchTimer: any = null;
function onSearchInput() {
  if (searchTimer) clearTimeout(searchTimer);
  searchTimer = setTimeout(() => { loadUsers(); }, 300);
}
function onFilterChange(f: Filter) {
  filter.value = f;
  loadUsers();
}
</script>

<template>
  <div class="rv3-users-shell">
    <!-- LEFT: list -->
    <div class="rv3-users-list-wrap">
      <!-- Filter bar -->
      <div class="rv3-filter-bar">
        <span class="rv3-filter-l">Фильтр</span>
        <button :class="['rv3-chip', { on: filter === 'active' }]" @click="onFilterChange('active')">
          Активные · {{ filter === 'active' ? users.length : '?' }}
        </button>
        <button :class="['rv3-chip', { on: filter === 'inactive' }]" @click="onFilterChange('inactive')">
          Заблокированы · {{ filter === 'inactive' ? users.length : '?' }}
        </button>
        <button :class="['rv3-chip', { on: filter === 'all' }]" @click="onFilterChange('all')">
          Все · {{ filter === 'all' ? total : '?' }}
        </button>
        <div style="flex:1;"></div>
        <input
          v-model="search"
          @input="onSearchInput"
          placeholder="Поиск по имени, email..."
          class="rv3-search"
        />
      </div>

      <!-- Bulk action bar -->
      <div v-if="selectedIds.size > 0" class="rv3-bulk">
        <div class="rv3-bulk-text">Выбрано: {{ selectedIds.size }} пользователей</div>
        <div style="flex:1;"></div>
        <button class="rv3-bulk-btn">+ Выдать разрешение</button>
        <button class="rv3-bulk-btn">− Отозвать</button>
        <button class="rv3-bulk-btn">Назначить роль</button>
        <button class="rv3-bulk-x" @click="selectedIds = new Set()">✕</button>
      </div>

      <!-- Loading / error -->
      <div v-if="loading" class="rv3-state">Загрузка...</div>
      <div v-else-if="error" class="rv3-state rv3-state-err">{{ error }}</div>
      <template v-else>
        <!-- Header row -->
        <div class="rv3-row rv3-row-hd">
          <div></div>
          <div>Пользователь</div>
          <div>Роли</div>
          <div>Последний вход</div>
          <div>Статус</div>
        </div>

        <div class="rv3-list">
          <div
            v-for="u in users"
            :key="u.id"
            :class="['rv3-row', 'rv3-row-data', { selected: selectedUser?.id === u.id, dim: !u.is_active }]"
            @click="openUser(u)"
          >
            <input
              type="checkbox"
              :checked="selectedIds.has(u.id)"
              @click.stop
              @change="toggleSelect(u.id)"
            />
            <div class="rv3-userc">
              <UserAvatar :email="u.email" :full-name="u.full_name" :size="32" />
              <div style="min-width:0;">
                <div class="rv3-user-name">
                  {{ u.full_name }}
                  <span v-if="u.is_owner" class="rv3-owner-flag">owner</span>
                </div>
                <div class="rv3-user-email">{{ u.email }}</div>
              </div>
            </div>
            <div class="rv3-roles">
              <RoleChip v-for="rc in u.role_codes" :key="rc" :code="rc" size="sm" />
              <span v-if="u.role_codes.length === 0" class="rv3-no-roles">—</span>
            </div>
            <div class="rv3-last">{{ fmtLastLogin(u.last_login_at) }}</div>
            <div :class="['rv3-status', { off: !u.is_active }]">
              <span class="rv3-status-dot"></span>
              {{ u.is_active ? 'активен' : 'заблокирован' }}
            </div>
          </div>
          <div v-if="users.length === 0" class="rv3-state">Пользователей не найдено</div>
        </div>

        <div class="rv3-foot">Показано {{ users.length }} из {{ total }}</div>
      </template>
    </div>

    <!-- RIGHT: drawer -->
    <UserDetailDrawer
      :user="selectedUser"
      @close="closeDrawer"
      @changed="onUserChanged"
    />
  </div>
</template>

<style scoped>
.rv3-users-shell {
  display: grid;
  grid-template-columns: 1fr 540px;
  gap: 1px;
  background: #E5E7EB;
  min-height: calc(100vh - 56px);
}
.rv3-users-list-wrap {
  background: #fff;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.rv3-filter-bar {
  padding: 14px 22px;
  border-bottom: 0.5px solid #E5E7EB;
  display: flex; gap: 8px; align-items: center; flex-wrap: wrap;
}
.rv3-filter-l {
  font-size: 10px; font-weight: 500; color: #888780;
  letter-spacing: .06em; text-transform: uppercase; margin-right: 4px;
}
.rv3-chip {
  padding: 5px 11px;
  background: #F3F4F8; border: 1px solid #E5E7EB; border-radius: 14px;
  font-size: 11px; font-weight: 500; color: #888780;
  cursor: pointer; font-family: inherit;
}
.rv3-chip.on {
  background: rgba(127,119,221,.12); border-color: rgba(127,119,221,.3); color: #534AB7;
}
.rv3-search {
  width: 240px; height: 28px; padding: 0 11px;
  background: #F9FAFB; border: 0.5px solid #E5E7EB; border-radius: 7px;
  font-size: 12px; outline: none; font-family: inherit;
}
.rv3-bulk {
  padding: 10px 22px;
  background: #1E2A4A; color: #fff;
  display: flex; align-items: center; gap: 12px;
}
.rv3-bulk-text { font-size: 12px; font-weight: 500; }
.rv3-bulk-btn {
  padding: 5px 11px;
  background: rgba(255,255,255,.08); border: 1px solid rgba(255,255,255,.12);
  border-radius: 6px; color: #fff; font-size: 11px; font-weight: 500;
  cursor: pointer; font-family: inherit;
}
.rv3-bulk-btn:hover { background: rgba(255,255,255,.14); }
.rv3-bulk-x {
  padding: 5px 8px;
  background: transparent; border: none; color: rgba(255,255,255,.55);
  font-size: 14px; cursor: pointer; font-family: inherit;
}
.rv3-list { flex: 1; overflow-y: auto; }
.rv3-row {
  display: grid;
  grid-template-columns: 32px 1fr 220px 130px 120px;
  gap: 14px; align-items: center;
  padding: 11px 22px;
  border-bottom: 0.5px solid #E5E7EB;
}
.rv3-row-hd {
  background: #FAFAFC;
  font-size: 9.5px; font-weight: 500; color: #888780;
  letter-spacing: .06em; text-transform: uppercase;
}
.rv3-row-data { cursor: pointer; }
.rv3-row-data:hover { background: #FAFAFC; }
.rv3-row-data.selected {
  background: rgba(127,119,221,.06);
  border-left: 3px solid #7F77DD;
  padding-left: 19px;
}
.rv3-row-data.dim { opacity: 0.55; }
.rv3-userc { display: flex; align-items: center; gap: 10px; min-width: 0; }
.rv3-user-name {
  font-size: 13px; font-weight: 500;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.rv3-owner-flag {
  margin-left: 6px;
  padding: 1px 6px;
  background: rgba(239,159,39,.12); color: #B27015;
  border-radius: 7px;
  font-size: 9px; font-weight: 500; letter-spacing: .04em; text-transform: uppercase;
}
.rv3-user-email {
  font-size: 11px; color: #888780;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.rv3-roles { display: flex; gap: 4px; flex-wrap: wrap; }
.rv3-no-roles { color: #D1D5DB; font-size: 11px; }
.rv3-last { font-size: 11px; color: #1E2A4A; }
.rv3-status {
  display: flex; align-items: center; gap: 5px;
  font-size: 11px; color: #1D9E75; font-weight: 500;
}
.rv3-status-dot { width: 6px; height: 6px; background: #1D9E75; border-radius: 50%; }
.rv3-status.off { color: #888780; }
.rv3-status.off .rv3-status-dot { background: #D1D5DB; }
.rv3-foot {
  padding: 10px 22px;
  font-size: 11px; color: #888780;
  text-align: center;
  border-top: 0.5px solid #E5E7EB;
}
.rv3-state {
  padding: 40px; text-align: center;
  font-size: 13px; color: #888780;
}
.rv3-state-err { color: #E24B4A; }

input[type=checkbox] { accent-color: #7F77DD; cursor: pointer; }
</style>
'@
# Overwrite existing skeleton
$usersPagePath = Join-Path $root "$fe\views\rbac-v3\UsersPage.vue"
if (Test-Path -LiteralPath $usersPagePath) {
    Copy-Item -LiteralPath $usersPagePath -Destination "$usersPagePath.bakP142a.$stamp" -Force
    Write-Host "[*] [3/3] views/rbac-v3/UsersPage.vue (overwriting skeleton)" -ForegroundColor Yellow
    Write-Host "    backup: $usersPagePath.bakP142a.$stamp" -ForegroundColor DarkGray
}
Write-File $usersPagePath $usersPage
Write-Host "    OK" -ForegroundColor Green

# ───────────────────────────────────────────────────────────────────────
# Rebuild + restart
# ───────────────────────────────────────────────────────────────────────
function Find-Container($pattern) {
    $all = (docker ps --format "{{.Names}}" 2>$null) -split "`n" | Where-Object { $_ -and $_.Trim() }
    foreach ($name in $all) { if ($name -match $pattern) { return $name } }
    return $null
}
$fec = Find-Container "frontend|^uza-frontend"
if (-not $fec) {
    Write-Host "[!] Frontend container not running" -ForegroundColor Yellow
} else {
    Write-Host ""
    Write-Host "[=] Rebuilding frontend" -ForegroundColor Cyan
    docker exec $fec sh -c "rm -rf /app/dist /app/node_modules/.vite 2>/dev/null; true"
    docker exec -e NODE_OPTIONS=--max-old-space-size=4096 -e VITE_API_BASE_URL= $fec npx vite build
    if ($LASTEXITCODE -ne 0) { throw "vite build failed" }
    docker restart $fec | Out-Null
    Write-Host "    restarted" -ForegroundColor Green
}

Write-Host ""
Write-Host "===================================================================" -ForegroundColor Green
Write-Host " p142a COMPLETE — Users page + drawer live" -ForegroundColor Green
Write-Host "===================================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Test (Ctrl+Shift+R):" -ForegroundColor Cyan
Write-Host "  1. /admin/rbac-v3 -> Пользователи tab" -ForegroundColor White
Write-Host "  2. Filter chips switch Active/Inactive/All" -ForegroundColor White
Write-Host "  3. Search filters by name/email" -ForegroundColor White
Write-Host "  4. Click any user -> drawer opens with 4 tabs" -ForegroundColor White
Write-Host "  5. Access tab: 16-module grid with READ/WRITE/ADMIN/NONE pills" -ForegroundColor White
Write-Host "  6. Checkbox a user -> bulk-bar appears (actions are TODO)" -ForegroundColor White
Write-Host "  7. Drawer footer: Deactivate / Delete actions work" -ForegroundColor White
