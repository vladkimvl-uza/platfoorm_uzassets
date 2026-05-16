<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { rbacV3Api } from '@/api/rbacV3';
import type { RbacV3UserBrief } from '@/api/rbacV3';
import UserAvatar from '@/components/rbac-v3/UserAvatar.vue';
import RoleChip from '@/components/rbac-v3/RoleChip.vue';
import UserDetailDrawer from './UserDetailDrawer.vue';
import BulkRolePickerModal from '@/components/rbac-v3/BulkRolePickerModal.vue';

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
const showBulk = ref(false);

function onExternalRefresh() { loadUsers(); }
onMounted(() => {
  loadUsers();
  window.addEventListener('rbac-v3:users-changed', onExternalRefresh);
});
import { onBeforeUnmount } from 'vue';
onBeforeUnmount(() => {
  window.removeEventListener('rbac-v3:users-changed', onExternalRefresh);
});

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
        <button class="rv3-bulk-btn" @click="showBulk = true">Назначить роль</button>
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
      @open-user="(id) => { const u = users.find(x => x.id === id); if (u) openUser(u); }"
    />

    <BulkRolePickerModal
      v-if="showBulk"
      :selected-ids="Array.from(selectedIds)"
      @close="showBulk = false"
      @done="() => { selectedIds = new Set(); loadUsers(); }"
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