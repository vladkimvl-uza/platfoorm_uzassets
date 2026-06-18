<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { rbacV3Api } from '@/api/rbacV3';
import type { RbacV3UserBrief } from '@/api/rbacV3';
import UserAvatar from '@/components/rbac-v3/UserAvatar.vue';
import UserCardAnchor from '@/components/user/UserCardAnchor.vue';
import RoleChip from '@/components/rbac-v3/RoleChip.vue';
import UserAffiliationBadge from '@/components/rbac-v3/UserAffiliationBadge.vue';
import UserDetailDrawer from './UserDetailDrawer.vue';
import BulkRolePickerModal from '@/components/rbac-v3/BulkRolePickerModal.vue';
import BIcon from '@/components/broadcasts/BIcon.vue';
import { presenceStatus } from '@/composables/usePresence';
import { useConfirm } from '@/composables/useConfirm';

const { confirmDialog } = useConfirm();

const users = ref<RbacV3UserBrief[]>([]);
const total = ref(0);
const loading = ref(false);
const error = ref<string | null>(null);
const search = ref('');
type Filter = 'active' | 'inactive' | 'all' | 'pwd_change';
const filter = ref<Filter>('active');
const PWD_AGE_WARN_DAYS = 60;
const PWD_AGE_CRIT_DAYS = 90;

function pwdAgeDays(u: RbacV3UserBrief): number | null {
  const v = (u as any).password_changed_at as string | null | undefined;
  if (!v) return null;
  return Math.floor((Date.now() - new Date(v).getTime()) / 86400000);
}
function pwdNeedsAttention(u: RbacV3UserBrief): boolean {
  if ((u as any).must_change_password) return true;
  const age = pwdAgeDays(u);
  return age !== null && age >= PWD_AGE_WARN_DAYS;
}
function pwdSeverity(u: RbacV3UserBrief): 'crit' | 'warn' | null {
  if ((u as any).must_change_password) return 'crit';
  const age = pwdAgeDays(u);
  if (age === null) return null;
  if (age >= PWD_AGE_CRIT_DAYS) return 'crit';
  if (age >= PWD_AGE_WARN_DAYS) return 'warn';
  return null;
}
function pwdLabel(u: RbacV3UserBrief): string {
  if ((u as any).must_change_password) return 'сменить';
  const age = pwdAgeDays(u);
  if (age === null) return '';
  return age + ' дн';
}
const selectedIds = ref<Set<string>>(new Set());
const selectedUser = ref<RbacV3UserBrief | null>(null);

// Защитный потолок выборки. Пагинации тут нет, поэтому при превышении
// показываем явное предупреждение (truncated), а клиентские счётчики/фильтры
// считаются по ЗАГРУЖЕННОМУ набору — нельзя выдавать их за полную картину.
const USERS_LIMIT = 500; // бэкенд-максимум listUsers (limit le=500) — выше даёт 422
const truncated = ref(false);

async function loadUsers(silent = false) {
  if (!silent) loading.value = true;
  error.value = null;
  try {
    const opts: any = { limit: USERS_LIMIT };
    if (filter.value === 'active') opts.is_active = true;
    if (filter.value === 'inactive') opts.is_active = false;
    if (search.value.trim()) opts.search = search.value.trim();
    const resp = await rbacV3Api.listUsers(opts);
    users.value = resp.items;
    total.value = resp.total;
    truncated.value = resp.items.length >= USERS_LIMIT || resp.total > resp.items.length;
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 'Не удалось загрузить пользователей';
  } finally {
    if (!silent) loading.value = false;
  }
}
const showBulk = ref(false);

function onExternalRefresh() { loadUsers(); }
// Тихий polling presence/данных — обновляет точки online/away/offline без
// мигания спиннера (presenceStatus время-зависим, нужен re-render).
let presenceTimer: number | undefined;
onMounted(() => {
  loadUsers();
  window.addEventListener('rbac-v3:users-changed', onExternalRefresh);
  presenceTimer = window.setInterval(() => loadUsers(true), 45000);
});
import { onBeforeUnmount } from 'vue';
onBeforeUnmount(() => {
  window.removeEventListener('rbac-v3:users-changed', onExternalRefresh);
  if (presenceTimer) window.clearInterval(presenceTimer);
});

const counts = computed(() => ({
  active: users.value.filter(u => u.is_active).length,
  inactive: users.value.filter(u => !u.is_active).length,
  pwd_change: users.value.filter(pwdNeedsAttention).length,
}));

const visibleUsers = computed(() => {
  if (filter.value === 'pwd_change') return users.value.filter(pwdNeedsAttention);
  return users.value;
});

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

// Колонка показывает ПОСЛЕДНЮЮ АКТИВНОСТЬ (last_seen_at, обновляется heartbeat'ом
// пока вкладка открыта), а не момент логина: при долгоживущей сессии / refresh-
// токенах last_login_at может быть «недели назад», хотя юзер заходит каждый день.
// Tooltip раскрывает точные значения активности и логина.
function lastActivityTitle(u: any): string {
  const seen = u.last_seen_at ? `Последняя активность: ${new Date(u.last_seen_at).toLocaleString('ru-RU')}` : 'Активности ещё не было';
  const login = u.last_login_at ? `Последний вход: ${new Date(u.last_login_at).toLocaleString('ru-RU')}` : 'Ни разу не входил';
  return `${seen}\n${login}`;
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

// ── Мульти-удаление (деактивация) выбранных ──
const bulkBusy = ref(false);
async function bulkDeactivate() {
  const ids = Array.from(selectedIds.value);
  if (ids.length === 0) return;
  if (!(await confirmDialog({ message: `Деактивировать ${ids.length} пользовател${ids.length === 1 ? 'я' : 'ей'}? Их активные сессии будут отозваны (можно реактивировать позже).`, danger: true }))) return;
  bulkBusy.value = true;
  let ok = 0; const failed: string[] = [];
  for (const id of ids) {
    try { await rbacV3Api.deactivate(id); ok++; }
    catch (e: any) { failed.push(e?.response?.data?.detail || id); }
  }
  bulkBusy.value = false;
  selectedIds.value = new Set();
  await loadUsers();
  if (failed.length) error.value = `Деактивировано ${ok}, не удалось ${failed.length}: ${failed[0]}`;
}
</script>

<template>
  <div class="rv3-users-shell" :class="{ 'rv3-detail-open': selectedUser }">
    <!-- LEFT: list -->
    <div class="rv3-users-list-wrap">
      <!-- Filter bar -->
      <div class="rv3-filter-bar">
        <span class="rv3-filter-l">Фильтр</span>
        <button :class="['rv3-chip', { on: filter === 'active' }]" @click="onFilterChange('active')">
          Активные<span v-if="filter === 'active'" class="rv3-chip-n">{{ users.length }}</span>
        </button>
        <button :class="['rv3-chip', { on: filter === 'inactive' }]" @click="onFilterChange('inactive')">
          Заблокированы<span v-if="filter === 'inactive'" class="rv3-chip-n">{{ users.length }}</span>
        </button>
        <button :class="['rv3-chip', { on: filter === 'all' }]" @click="onFilterChange('all')">
          Все<span v-if="filter === 'all'" class="rv3-chip-n">{{ total }}</span>
        </button>
        <button
          :class="['rv3-chip', 'rv3-chip-warn', { on: filter === 'pwd_change' }]"
          :title="`Просрочен пароль (≥${PWD_AGE_WARN_DAYS}д) или установлен флаг смены`"
          @click="onFilterChange('pwd_change')"
        >
          <BIcon name="lock" :size="12" /> Пароль<span
            v-if="counts.pwd_change"
            class="rv3-chip-n warn"
            :title="truncated ? 'Среди загруженных пользователей (список усечён)' : 'Среди загруженных пользователей'"
          >{{ counts.pwd_change }}</span>
        </button>
        <div style="flex:1;"></div>
        <input
          v-model="search"
          @input="onSearchInput"
          type="search"
          name="rv3-user-search-q"
          autocomplete="off"
          autocorrect="off"
          autocapitalize="off"
          spellcheck="false"
          data-lpignore="true"
          data-1p-ignore
          placeholder="Поиск по имени, email..."
          class="rv3-search"
        />
      </div>

      <!-- Bulk action bar -->
      <div v-if="selectedIds.size > 0" class="rv3-bulk">
        <div class="rv3-bulk-text">Выбрано: {{ selectedIds.size }}</div>
        <div style="flex:1;"></div>
        <button class="rv3-bulk-btn" @click="showBulk = true">Назначить роль</button>
        <button class="rv3-bulk-btn rv3-bulk-danger" :disabled="bulkBusy" @click="bulkDeactivate">
          <BIcon name="trash" :size="13" /> {{ bulkBusy ? 'Деактивация…' : 'Деактивировать' }}
        </button>
        <button class="rv3-bulk-x" @click="selectedIds = new Set()" title="Снять выделение"><BIcon name="x" :size="14" /></button>
      </div>

      <!-- Loading / error -->
      <div v-if="loading" class="rv3-state">Загрузка...</div>
      <div v-else-if="error" class="rv3-state rv3-state-err">{{ error }}</div>
      <template v-else>
        <!-- Усечение выборки: счётчики/фильтры ниже считаются клиентски по
             загруженному набору и не отражают всех пользователей. -->
        <div v-if="truncated" class="rv3-trunc">
          <BIcon name="info-circle" :size="13" style="flex:none;margin-top:1px" />
          Загружено {{ users.length }} из {{ total }} пользователей. Список усечён —
          фильтры и счётчики (Активные / Заблокированы / Пароль) считаются только по загруженным.
          Уточните поиск.
        </div>
        <!-- Header row -->
        <div class="rv3-row rv3-row-hd">
          <div></div>
          <div>Пользователь</div>
          <div>Роли</div>
          <div>Активность</div>
          <div>Пароль</div>
          <div>Статус</div>
        </div>

        <div class="rv3-list">
          <div
            v-for="u in visibleUsers"
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
              <UserCardAnchor :user-id="u.id" :preview="{ full_name: u.full_name, email: u.email }">
                <UserAvatar :email="u.email" :full-name="u.full_name" :size="32" :status="presenceStatus(u.last_seen_at)" />
              </UserCardAnchor>
              <div style="min-width:0;">
                <div class="rv3-user-name">
                  {{ u.full_name }}
                  <span v-if="u.is_owner" class="rv3-owner-flag">owner</span>
                </div>
                <div class="rv3-user-email">{{ u.email }}</div>
                <UserAffiliationBadge
                  v-if="u.department || u.job_title"
                  size="sm" style="margin-top:3px"
                  :department="u.department" :job-title="u.job_title"
                />
              </div>
            </div>
            <div class="rv3-roles">
              <RoleChip v-for="rc in u.role_codes" :key="rc" :code="rc" size="sm" />
              <span v-if="u.role_codes.length === 0" class="rv3-no-roles">—</span>
            </div>
            <div class="rv3-last" :title="lastActivityTitle(u)">{{ fmtLastLogin(u.last_seen_at) }}</div>
            <div class="rv3-pwd">
              <span
                v-if="pwdSeverity(u)"
                :class="['rv3-pwd-pill', 'rv3-pwd-' + pwdSeverity(u)]"
                :title="(u as any).password_changed_at ? 'Последняя смена: ' + new Date((u as any).password_changed_at).toLocaleString('ru-RU') : 'Никогда не менялся'"
              >{{ pwdLabel(u) }}</span>
              <span v-else-if="(u as any).password_changed_at" class="rv3-pwd-ok" :title="new Date((u as any).password_changed_at).toLocaleString('ru-RU')">
                ✓ {{ pwdAgeDays(u) }} дн
              </span>
              <span v-else class="rv3-no-roles">—</span>
            </div>
            <div :class="['rv3-status', { off: !u.is_active }]">
              <span class="rv3-status-dot"></span>
              {{ u.is_active ? 'активен' : 'заблокирован' }}
            </div>
          </div>
          <div v-if="visibleUsers.length === 0" class="rv3-state">Пользователей не найдено</div>
        </div>

        <div class="rv3-foot">
          Показано {{ visibleUsers.length }}
          <template v-if="truncated"> · загружено {{ users.length }} из {{ total }}</template>
          <template v-else> из {{ total }}</template>
        </div>
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
  /* Без выбранного пользователя список занимает всю ширину —
     не резервируем пустую 540px-колонку (раньше показывалась серой
     панелью и поджимала таблицу на широких/нестандартных разрешениях). */
  grid-template-columns: 1fr;
  gap: 1px;
  background: var(--border-hard);
  min-height: calc(100vh - 56px);
  transition: grid-template-columns 0.32s cubic-bezier(0.34, 1.2, 0.64, 1);
}
.rv3-users-shell.rv3-detail-open {
  grid-template-columns: 1fr 540px;
}
/* На промежуточных ширинах деталь не должна раздавливать таблицу списка */
@media (max-width: 1280px) {
  .rv3-users-shell.rv3-detail-open { grid-template-columns: 1fr 460px; }
}
/* При открытой detail-панели на неширокких экранах список сжимается до
   навигационного столбца: пользователь + статус. Роли / последний вход /
   пароль и так показаны в самой панели — не дублируем и не режем колонку
   «Статус». На очень широких (≥1601px) колонки умещаются рядом с панелью. */
@media (max-width: 1600px) {
  .rv3-users-shell.rv3-detail-open .rv3-row {
    grid-template-columns: 32px 1fr 110px;
  }
  .rv3-users-shell.rv3-detail-open .rv3-row > :nth-child(3),
  .rv3-users-shell.rv3-detail-open .rv3-row > :nth-child(4),
  .rv3-users-shell.rv3-detail-open .rv3-row > :nth-child(5) {
    display: none;
  }
}
.rv3-users-list-wrap {
  background: var(--bg1, #fff);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.rv3-filter-bar {
  padding: 14px 22px;
  border-bottom: 0.5px solid var(--border-hard);
  display: flex; gap: 8px; align-items: center; flex-wrap: wrap;
}
.rv3-filter-l {
  font-size: 10px; font-weight: 500; color: var(--t3, var(--t-muted));
  letter-spacing: .06em; text-transform: uppercase; margin-right: 4px;
}
.rv3-chip {
  padding: 5px 11px;
  background: #F3F4F8; border: 1px solid var(--border-hard); border-radius: 14px;
  font-size: 11px; font-weight: 500; color: var(--t3, var(--t-muted));
  cursor: pointer; font-family: inherit;
  display: inline-flex; align-items: center; gap: 5px;
  transition: background .14s, border-color .14s, color .14s;
}
.rv3-chip:hover { background: #ECEEF5; color: var(--t2, #334155); }
.rv3-chip.on {
  background: rgba(127,119,221,.12); border-color: rgba(127,119,221,.3); color: var(--p-deep);
}
.rv3-chip-n {
  font-size: 10px; font-weight: 700; font-variant-numeric: tabular-nums;
  background: rgba(127,119,221,.18); color: var(--p-deep);
  padding: 0 6px; border-radius: 8px; line-height: 16px; min-width: 16px; text-align: center;
}
.rv3-chip-n.warn { background: rgba(239,159,39,.18); color: #B27015; }
.rv3-search {
  width: 240px; height: 28px; padding: 0 11px;
  background: var(--bg2, #F9FAFB); border: 0.5px solid var(--border-hard); border-radius: 7px;
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
  display: inline-flex; align-items: center; gap: 5px;
}
.rv3-bulk-btn:hover { background: rgba(255,255,255,.14); }
.rv3-bulk-danger { background: rgba(226,75,74,.22); border-color: rgba(226,75,74,.5); }
.rv3-bulk-danger:hover { background: rgba(226,75,74,.34); }
.rv3-bulk-danger:disabled { opacity: .6; cursor: default; }
.rv3-bulk-x {
  padding: 5px 8px;
  background: transparent; border: none; color: rgba(255,255,255,.6);
  cursor: pointer; font-family: inherit;
  display: inline-flex; align-items: center;
}
.rv3-bulk-x:hover { color: #fff; }
.rv3-list { flex: 1; overflow-y: auto; }
.rv3-row {
  display: grid;
  grid-template-columns: 32px 1fr 220px 110px 90px 110px;
  gap: 12px; align-items: center;
  padding: 11px 22px;
  border-bottom: 0.5px solid var(--border-hard);
}
.rv3-row-hd {
  background: var(--bg2, #FAFAFC);
  font-size: 9.5px; font-weight: 500; color: var(--t3, var(--t-muted));
  letter-spacing: .06em; text-transform: uppercase;
}
.rv3-row-data { cursor: pointer; position: relative; overflow: hidden; }
.rv3-row-data:hover { background: var(--bg2, #FAFAFC); }
.rv3-row-data.selected {
  background: rgba(127,119,221,.06);
}
.rv3-row-data.selected::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0;
  height: 2px; background: #7F77DD;
  animation: uzaStripeDrawIn .4s var(--ease-standard) both;
  transform-origin: left center;
  pointer-events: none;
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
  font-size: 11px; color: var(--t3, var(--t-muted));
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.rv3-roles { display: flex; gap: 4px; flex-wrap: wrap; }
.rv3-no-roles { color: #D1D5DB; font-size: 11px; }
.rv3-last { font-size: 11px; color: var(--t1, #1E2A4A); }
.rv3-status {
  display: flex; align-items: center; gap: 5px;
  font-size: 11px; color: var(--green); font-weight: 500;
}
.rv3-status-dot { width: 6px; height: 6px; background: var(--green); border-radius: 50%; }
.rv3-status.off { color: var(--t3, var(--t-muted)); }
.rv3-status.off .rv3-status-dot { background: #D1D5DB; }
.rv3-foot {
  padding: 10px 22px;
  font-size: 11px; color: var(--t3, var(--t-muted));
  text-align: center;
  border-top: 0.5px solid var(--border-hard);
}
.rv3-trunc {
  display: flex; align-items: flex-start; gap: 8px;
  padding: 9px 22px;
  background: rgba(239,159,39,.1);
  border-bottom: 0.5px solid rgba(239,159,39,.28);
  color: #B27015; font-size: 11.5px; line-height: 1.45;
}
.rv3-state {
  padding: 40px; text-align: center;
  font-size: 13px; color: var(--t3, var(--t-muted));
}
.rv3-state-err { color: var(--sev-high); }

input[type=checkbox] { accent-color: #7F77DD; cursor: pointer; }

/* Password column pills */
.rv3-pwd { font-size: 11px; }
.rv3-pwd-pill {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 10.5px;
  font-weight: 500;
  letter-spacing: .02em;
  cursor: help;
}
.rv3-pwd-crit {
  background: rgba(226,75,74,.12);
  color: #B81F1E;
  border: 1px solid rgba(226,75,74,.22);
}
.rv3-pwd-warn {
  background: rgba(239,159,39,.14);
  color: #B27015;
  border: 1px solid rgba(239,159,39,.25);
}
.rv3-pwd-ok {
  color: var(--t3, var(--t-muted));
  font-size: 10.5px;
  cursor: help;
}
.rv3-chip-warn.on {
  background: rgba(239,159,39,.14);
  border-color: rgba(239,159,39,.32);
  color: #B27015;
}

/* ═══════════ MOBILE (Phase 2) ═══════════ */
@media (max-width: 900px) {
  /* Detail-панель уходит под список (стек) */
  .rv3-users-shell,
  .rv3-users-shell.rv3-detail-open { grid-template-columns: 1fr; }
}
@media (max-width: 640px) {
  /* Строка-пользователь: оставляем аватар + имя + статус, остальное — в дровере */
  .rv3-row { grid-template-columns: 32px 1fr auto; column-gap: 8px; padding: 11px 14px; }
  .rv3-row > :nth-child(3),
  .rv3-row > :nth-child(4),
  .rv3-row > :nth-child(5) { display: none; }
}
</style>
