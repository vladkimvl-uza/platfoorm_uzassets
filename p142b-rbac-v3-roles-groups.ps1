# =====================================================================
# p142b-rbac-v3-roles-groups.ps1   (RBAC v3 session 3 — part 2)
# =====================================================================
# Adds real implementations for RolesPage + GroupsPage.
# Uses existing backend endpoints:
#   GET    /rbac/roles                      -> RoleBrief[]
#   GET    /rbac/roles/{code}               -> RoleDetail
#   PATCH  /rbac/roles/{code}/permissions   -> RoleDetail
#   GET    /admin/rbac-v2/groups            -> GroupRead[]
#   GET    /admin/rbac-v2/groups/{id}       -> GroupDetail
#   POST   /admin/rbac-v2/groups            -> GroupRead
#   PATCH  /admin/rbac-v2/groups/{id}       -> GroupRead
#   DELETE /admin/rbac-v2/groups/{id}       -> 204
#   PUT    /admin/rbac-v2/groups/{id}/members      -> GroupDetail
#   PUT    /admin/rbac-v2/groups/{id}/permissions  -> GroupDetail
#
# Note: backend POST /rbac/roles + DELETE /rbac/roles/{code} are NOT
# yet implemented — they are scheduled for session 4 backend layer.
# Until then, RolesPage shows "Roles are managed in code" hint for
# create/delete buttons; permission editing works fully.
# =====================================================================

$ErrorActionPreference = "Stop"
$enc = New-Object System.Text.UTF8Encoding($false)
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$root = $PSScriptRoot
if (-not $root) { $root = (Get-Location).Path }

function Read-File($p)  { return [System.IO.File]::ReadAllText($p, $enc) }
function Write-File($p, $text) { [System.IO.File]::WriteAllText($p, $text, $enc) }
function Ensure-Dir($d) { if (-not (Test-Path -LiteralPath $d)) { New-Item -ItemType Directory -Path $d -Force | Out-Null } }
function Write-NewFile($path, $content, $label, [switch]$Overwrite) {
    Write-Host "[*] $label" -ForegroundColor Yellow
    if (Test-Path -LiteralPath $path) {
        if (-not $Overwrite) {
            Write-Host "    SKIP: file already exists" -ForegroundColor DarkGray
            return
        }
        Copy-Item -LiteralPath $path -Destination "$path.bakP142b.$stamp" -Force
        Write-Host "    backup: $path.bakP142b.$stamp" -ForegroundColor DarkGray
    }
    Ensure-Dir (Split-Path $path -Parent)
    Write-File $path $content
    Write-Host "    OK" -ForegroundColor Green
}

$fe = "frontend\src"

# ───────────────────────────────────────────────────────────────────────
# [1/3] Extend api/rbacV3.ts — add roles + groups
# ───────────────────────────────────────────────────────────────────────
$apiAddon = @'

// ─── Roles ───────────────────────────────────────────────────────

export interface RbacV3RolePerm {
  id: string;
  code: string;
  description?: string | null;
  category?: string | null;
}
export interface RbacV3Role {
  id: string;
  code: string;
  name_ru: string;
  name_en: string | null;
  description_ru: string | null;
  is_system: boolean;
  sort_order: number;
  permission_count: number;
}
export interface RbacV3RoleDetail extends RbacV3Role {
  permissions: RbacV3RolePerm[];
}

export const rolesApi = {
  async list(): Promise<RbacV3Role[]> {
    const { data } = await api.get<RbacV3Role[]>('/rbac/roles');
    return data;
  },
  async get(code: string): Promise<RbacV3RoleDetail> {
    const { data } = await api.get<RbacV3RoleDetail>(`/rbac/roles/${code}`);
    return data;
  },
  async updatePermissions(code: string, permission_codes: string[]): Promise<RbacV3RoleDetail> {
    const { data } = await api.patch<RbacV3RoleDetail>(`/rbac/roles/${code}/permissions`, { permission_codes });
    return data;
  },
};

// ─── Groups ──────────────────────────────────────────────────────

export interface RbacV3Group {
  id: string;
  code: string;
  name: string;
  description: string | null;
  organization_id: string | null;
  department: string | null;
  member_count: number;
  permission_count: number;
  role_codes: string[];
}
export interface RbacV3GroupMember {
  id: string;
  email: string;
  full_name: string;
}
export interface RbacV3GroupPerm {
  code: string;
  description?: string | null;
}
export interface RbacV3GroupDetail extends RbacV3Group {
  members: RbacV3GroupMember[];
  permissions: RbacV3GroupPerm[];
  roles: string[];
}

export const groupsApi = {
  async list(): Promise<RbacV3Group[]> {
    const { data } = await api.get<RbacV3Group[]>('/admin/rbac-v2/groups');
    return data;
  },
  async get(id: string): Promise<RbacV3GroupDetail> {
    const { data } = await api.get<RbacV3GroupDetail>(`/admin/rbac-v2/groups/${id}`);
    return data;
  },
  async create(payload: { code: string; name: string; description?: string; department?: string }): Promise<RbacV3Group> {
    const { data } = await api.post<RbacV3Group>('/admin/rbac-v2/groups', payload);
    return data;
  },
  async update(id: string, payload: { name?: string; description?: string; department?: string }): Promise<RbacV3Group> {
    const { data } = await api.patch<RbacV3Group>(`/admin/rbac-v2/groups/${id}`, payload);
    return data;
  },
  async remove(id: string): Promise<void> {
    await api.delete(`/admin/rbac-v2/groups/${id}`);
  },
  async setMembers(id: string, user_ids: string[]): Promise<RbacV3GroupDetail> {
    const { data } = await api.put<RbacV3GroupDetail>(`/admin/rbac-v2/groups/${id}/members`, { user_ids });
    return data;
  },
  async setPermissions(id: string, permission_codes: string[]): Promise<RbacV3GroupDetail> {
    const { data } = await api.put<RbacV3GroupDetail>(`/admin/rbac-v2/groups/${id}/permissions`, { permission_codes });
    return data;
  },
};

// ─── Helper: permissions <-> level on module conversion ──────────

import { MODULE_REGISTRY as _MODS } from '@/composables/usePermissions';

/**
 * Convert flat permission_codes back into per-module level map.
 * Inverse of deriveAccessMap on permissions only.
 */
export function permissionsToLevels(codes: string[]): Record<string, AccessLevel> {
  const out: Record<string, AccessLevel> = {};
  for (const m of _MODS) {
    const prefix = m.code + '.';
    const owned = codes.filter(c => c.startsWith(prefix));
    if (owned.length === 0) { out[m.code] = 'none'; continue; }
    if (owned.some(c => c.endsWith('.manage') || c.endsWith('.admin'))) out[m.code] = 'admin';
    else if (owned.some(c => /\.(edit|create|update|delete|write|approve)$/.test(c))) out[m.code] = 'write';
    else if (owned.some(c => c.endsWith('.view') || c.endsWith('.read'))) out[m.code] = 'read';
    else out[m.code] = 'none';
  }
  return out;
}

/**
 * Convert per-module level map back into flat permission_codes.
 * Used when saving role.permissions or group.permissions.
 * Strategy: produce canonical codes per level
 *   read  -> {module}.view
 *   write -> {module}.view + {module}.edit + {module}.export
 *   admin -> {module}.view + {module}.edit + {module}.export + {module}.manage
 */
export function levelsToPermissions(levels: Record<string, AccessLevel>): string[] {
  const codes: string[] = [];
  for (const [code, level] of Object.entries(levels)) {
    if (level === 'none') continue;
    codes.push(`${code}.view`);
    if (level === 'write' || level === 'admin') {
      codes.push(`${code}.edit`, `${code}.export`);
    }
    if (level === 'admin') {
      codes.push(`${code}.manage`);
    }
  }
  return codes;
}
'@

$apiPath = Join-Path $root "$fe\api\rbacV3.ts"
$apiSrc = Read-File $apiPath
if ($apiSrc.Contains('export const rolesApi')) {
    Write-Host "[*] [1/3] api/rbacV3.ts — roles/groups already added, skipping" -ForegroundColor DarkGray
} else {
    Copy-Item -LiteralPath $apiPath -Destination "$apiPath.bakP142b.$stamp" -Force
    Write-Host "[*] [1/3] api/rbacV3.ts — adding roles + groups" -ForegroundColor Yellow
    Write-File $apiPath ($apiSrc + $apiAddon)
    Write-Host "    OK" -ForegroundColor Green
}

# ───────────────────────────────────────────────────────────────────────
# [2/3] views/rbac-v3/RolesPage.vue — real implementation
# ───────────────────────────────────────────────────────────────────────
$rolesPage = @'
<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue';
import { rolesApi, permissionsToLevels, levelsToPermissions } from '@/api/rbacV3';
import type { RbacV3Role, RbacV3RoleDetail } from '@/api/rbacV3';
import type { AccessLevel } from '@/composables/usePermissions';
import RoleChip from '@/components/rbac-v3/RoleChip.vue';
import ModuleSelectGrid from '@/components/rbac-v3/ModuleSelectGrid.vue';

const roles = ref<RbacV3Role[]>([]);
const selectedCode = ref<string | null>(null);
const detail = ref<RbacV3RoleDetail | null>(null);
const levels = ref<Record<string, AccessLevel>>({});
const loading = ref(false);
const error = ref<string | null>(null);
const saving = ref(false);
const dirty = ref(false);
const description = ref('');

async function loadRoles() {
  try {
    roles.value = (await rolesApi.list()).sort((a, b) => a.sort_order - b.sort_order);
    if (!selectedCode.value && roles.value.length > 0) {
      selectedCode.value = roles.value[0].code;
    }
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 'Не удалось загрузить роли';
  }
}

async function loadDetail() {
  if (!selectedCode.value) { detail.value = null; return; }
  loading.value = true; error.value = null; dirty.value = false;
  try {
    detail.value = await rolesApi.get(selectedCode.value);
    description.value = detail.value.description_ru || '';
    levels.value = permissionsToLevels(detail.value.permissions.map(p => p.code));
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 'Ошибка загрузки роли';
  } finally {
    loading.value = false;
  }
}

onMounted(loadRoles);
watch(selectedCode, loadDetail);

function selectRole(code: string) {
  if (dirty.value && !confirm('Есть несохранённые изменения. Перейти к другой роли?')) return;
  selectedCode.value = code;
}

function onLevelChange(newLevels: Record<string, AccessLevel>) {
  levels.value = newLevels;
  dirty.value = true;
}

function setAllLevels(level: AccessLevel) {
  const next: Record<string, AccessLevel> = {};
  for (const code of Object.keys(levels.value)) next[code] = level;
  levels.value = next;
  dirty.value = true;
}

async function save() {
  if (!detail.value || !selectedCode.value) return;
  saving.value = true; error.value = null;
  try {
    const codes = levelsToPermissions(levels.value);
    detail.value = await rolesApi.updatePermissions(selectedCode.value, codes);
    levels.value = permissionsToLevels(detail.value.permissions.map(p => p.code));
    dirty.value = false;
    await loadRoles();
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 'Ошибка сохранения';
  } finally {
    saving.value = false;
  }
}

const ROLE_COLOR: Record<string, string> = {
  admin:'#E24B4A', ceo:'#EF9F27', debt:'#1D9E75',
  readonly:'#888780', imv_admin:'#378ADD',
};
function roleColor(code: string) { return ROLE_COLOR[code] || '#7F77DD'; }

const sysRoles = computed(() => roles.value.filter(r => r.is_system));
const customRoles = computed(() => roles.value.filter(r => !r.is_system));
</script>

<template>
  <div class="rv3-roles-shell">
    <!-- LEFT: list -->
    <div class="rv3-roles-list">
      <div class="rv3-rl-section">
        <div class="rv3-rl-section-hd">Системные · {{ sysRoles.length }}</div>
        <div
          v-for="r in sysRoles"
          :key="r.code"
          :class="['rv3-rl-item', { on: selectedCode === r.code }]"
          @click="selectRole(r.code)"
        >
          <div class="rv3-rl-row">
            <span class="rv3-rl-dot" :style="{ background: roleColor(r.code) }"></span>
            <span class="rv3-rl-name">{{ r.code }}</span>
            <svg width="10" height="10" viewBox="0 0 12 12" fill="none" stroke="#888780" stroke-width="1.5" style="margin-left:auto;flex-shrink:0;">
              <rect x="3" y="5" width="6" height="5" rx="1"/>
              <path d="M5 5V3a1 1 0 0 1 2 0v2"/>
            </svg>
          </div>
          <div class="rv3-rl-meta">{{ r.name_ru }} · {{ r.permission_count }} разреш.</div>
        </div>
      </div>

      <div class="rv3-rl-section" v-if="customRoles.length > 0">
        <div class="rv3-rl-section-hd">Пользовательские · {{ customRoles.length }}</div>
        <div
          v-for="r in customRoles"
          :key="r.code"
          :class="['rv3-rl-item', { on: selectedCode === r.code }]"
          @click="selectRole(r.code)"
        >
          <div class="rv3-rl-row">
            <span class="rv3-rl-dot" :style="{ background: roleColor(r.code) }"></span>
            <span class="rv3-rl-name">{{ r.code }}</span>
          </div>
          <div class="rv3-rl-meta">{{ r.name_ru }} · {{ r.permission_count }} разреш.</div>
        </div>
      </div>

      <button class="rv3-rl-add" disabled title="Создание ролей будет в сессии 4 (backend POST endpoint)">
        + Новая роль
      </button>
    </div>

    <!-- RIGHT: editor -->
    <div class="rv3-roles-edit">
      <div v-if="loading" class="rv3-state">Загрузка...</div>
      <div v-else-if="error" class="rv3-state rv3-err">{{ error }}</div>
      <template v-else-if="detail">
        <div class="rv3-edit-hd">
          <div class="rv3-edit-icon" :style="{ background: roleColor(detail.code) + '20', borderColor: roleColor(detail.code) + '50' }">
            <span class="rv3-rl-dot" :style="{ background: roleColor(detail.code), width: '14px', height: '14px' }"></span>
          </div>
          <div style="flex:1;">
            <div class="rv3-edit-title">
              {{ detail.name_ru }}
              <RoleChip :code="detail.code" size="sm" />
            </div>
            <div class="rv3-edit-meta">
              <span>code: <code>{{ detail.code }}</code></span>
              <span v-if="detail.is_system" class="rv3-sys">
                <svg width="10" height="10" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="5" width="6" height="5" rx="1"/><path d="M5 5V3a1 1 0 0 1 2 0v2"/></svg>
                системная
              </span>
              <span>· {{ detail.permission_count }} разрешений</span>
            </div>
          </div>
          <button
            class="rv3-save"
            :disabled="!dirty || saving"
            @click="save"
          >
            {{ saving ? 'Сохранение...' : (dirty ? 'Сохранить' : 'Сохранено') }}
          </button>
        </div>

        <div class="rv3-edit-section">
          <div class="rv3-edit-label">Описание</div>
          <textarea
            v-model="description"
            class="rv3-textarea"
            placeholder="Описание роли — для чего используется"
            disabled
            title="Редактирование описания будет в сессии 4"
          ></textarea>
        </div>

        <div class="rv3-edit-section">
          <div class="rv3-edit-label rv3-edit-label-row">
            <span>Доступ к модулям</span>
            <div class="rv3-quick">
              <button class="rv3-quick-btn rv3-quick-admin" @click="setAllLevels('admin')">ВСЕ ADMIN</button>
              <button class="rv3-quick-btn" @click="setAllLevels('read')">ВСЕ READ</button>
              <button class="rv3-quick-btn" @click="setAllLevels('none')">СБРОС</button>
            </div>
          </div>
          <ModuleSelectGrid
            :model-value="levels"
            :editable="true"
            :columns="4"
            @update:model-value="onLevelChange"
          />
        </div>

        <div class="rv3-edit-foot">
          <button class="rv3-btn rv3-btn-ghost" disabled title="Дублирование — сессия 4">Дублировать роль</button>
          <div style="flex:1"></div>
          <button
            v-if="!detail.is_system"
            class="rv3-btn rv3-btn-red"
            disabled
            title="Удаление ролей — сессия 4"
          >Удалить роль</button>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.rv3-roles-shell {
  display: grid;
  grid-template-columns: 300px 1fr;
  gap: 1px;
  background: #E5E7EB;
  min-height: calc(100vh - 56px);
}
.rv3-roles-list {
  background: #fff;
  padding: 16px 0;
  overflow-y: auto;
}
.rv3-rl-section + .rv3-rl-section { margin-top: 18px; }
.rv3-rl-section-hd {
  padding: 0 18px 8px;
  font-size: 10px; font-weight: 500; color: #888780;
  letter-spacing: .06em; text-transform: uppercase;
}
.rv3-rl-item {
  padding: 10px 18px;
  border-left: 3px solid transparent;
  cursor: pointer;
}
.rv3-rl-item:hover { background: #FAFAFC; }
.rv3-rl-item.on {
  background: rgba(127,119,221,.06);
  border-left-color: #7F77DD;
}
.rv3-rl-row { display: flex; align-items: center; gap: 8px; margin-bottom: 3px; }
.rv3-rl-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.rv3-rl-name { font-size: 13px; font-weight: 500; font-family: ui-monospace, 'SF Mono', Menlo, monospace; }
.rv3-rl-meta { font-size: 10.5px; color: #888780; }
.rv3-rl-add {
  margin: 14px 18px 0;
  padding: 9px 12px;
  background: transparent;
  border: 1px dashed #D1D5DB;
  border-radius: 8px;
  color: #888780;
  font-size: 12px; font-weight: 500;
  cursor: not-allowed;
  width: calc(100% - 36px);
  font-family: inherit;
}

.rv3-roles-edit { background: #fff; padding: 24px 28px; overflow-y: auto; }
.rv3-edit-hd {
  display: flex; align-items: flex-start; gap: 14px; margin-bottom: 18px;
}
.rv3-edit-icon {
  width: 42px; height: 42px; border-radius: 10px;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0; border: 1px solid;
}
.rv3-edit-title {
  font-size: 16px; font-weight: 500; letter-spacing: -.01em;
  display: flex; align-items: center; gap: 10px;
}
.rv3-edit-meta {
  font-size: 11px; color: #888780; margin-top: 3px;
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
}
.rv3-edit-meta code {
  font-family: ui-monospace, 'SF Mono', Menlo, monospace;
  color: #1E2A4A;
}
.rv3-sys {
  display: inline-flex; align-items: center; gap: 4px;
  color: #E24B4A;
}
.rv3-save {
  padding: 7px 14px;
  background: #1D9E75; color: #fff;
  border: none; border-radius: 8px;
  font-size: 12px; font-weight: 500;
  cursor: pointer; font-family: inherit;
}
.rv3-save:disabled {
  background: #E5E7EB; color: #888780; cursor: not-allowed;
}
.rv3-edit-section { margin-bottom: 18px; }
.rv3-edit-label {
  font-size: 10px; font-weight: 500; color: #888780;
  letter-spacing: .06em; text-transform: uppercase;
  margin-bottom: 6px;
}
.rv3-edit-label-row {
  display: flex; align-items: center; justify-content: space-between;
}
.rv3-textarea {
  width: 100%; padding: 9px 12px;
  border: 0.5px solid #E5E7EB; border-radius: 8px;
  font-size: 12px; color: #1E2A4A; outline: none;
  resize: vertical; min-height: 48px;
  font-family: inherit;
  background: #FAFAFC;
}
.rv3-quick { display: flex; gap: 4px; }
.rv3-quick-btn {
  padding: 3px 9px;
  background: #F3F4F8; color: #888780;
  border: none; border-radius: 10px;
  font-size: 9.5px; font-weight: 500;
  letter-spacing: .04em; cursor: pointer; font-family: inherit;
}
.rv3-quick-btn:hover { background: #E5E7EB; }
.rv3-quick-admin {
  background: rgba(29,158,117,.12) !important;
  color: #1D9E75 !important;
}
.rv3-edit-foot {
  margin-top: 24px;
  padding-top: 18px;
  border-top: 0.5px solid #E5E7EB;
  display: flex; gap: 8px; align-items: center;
}
.rv3-btn {
  padding: 7px 14px; border-radius: 8px;
  font-size: 12px; font-weight: 500;
  cursor: pointer; font-family: inherit;
}
.rv3-btn:disabled { opacity: .55; cursor: not-allowed; }
.rv3-btn-ghost { background: transparent; border: 1px solid #E5E7EB; color: #1E2A4A; }
.rv3-btn-red { background: #fff; border: 1px solid #E24B4A; color: #E24B4A; }
.rv3-state { padding: 60px; text-align: center; font-size: 13px; color: #888780; }
.rv3-err { color: #E24B4A; }
</style>
'@
Write-NewFile (Join-Path $root "$fe\views\rbac-v3\RolesPage.vue") $rolesPage "[2/3] views/rbac-v3/RolesPage.vue" -Overwrite

# ───────────────────────────────────────────────────────────────────────
# [3/3] views/rbac-v3/GroupsPage.vue — real implementation
# ───────────────────────────────────────────────────────────────────────
$groupsPage = @'
<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue';
import { groupsApi, rbacV3Api, permissionsToLevels, levelsToPermissions } from '@/api/rbacV3';
import type { RbacV3Group, RbacV3GroupDetail, RbacV3UserBrief } from '@/api/rbacV3';
import type { AccessLevel } from '@/composables/usePermissions';
import UserAvatar from '@/components/rbac-v3/UserAvatar.vue';
import ModuleSelectGrid from '@/components/rbac-v3/ModuleSelectGrid.vue';

const groups = ref<RbacV3Group[]>([]);
const selectedId = ref<string | null>(null);
const detail = ref<RbacV3GroupDetail | null>(null);
const levels = ref<Record<string, AccessLevel>>({});
const loading = ref(false);
const error = ref<string | null>(null);
const saving = ref(false);
const dirty = ref(false);

const editName = ref('');
const editDescription = ref('');
const editDepartment = ref('');

const showCreate = ref(false);
const newGroup = ref({ code: '', name: '', description: '', department: '' });

const showMemberPicker = ref(false);
const allUsers = ref<RbacV3UserBrief[]>([]);
const memberSearch = ref('');

async function loadGroups() {
  try {
    groups.value = (await groupsApi.list()).sort((a, b) => a.name.localeCompare(b.name));
    if (!selectedId.value && groups.value.length > 0) selectedId.value = groups.value[0].id;
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 'Не удалось загрузить группы';
  }
}
async function loadDetail() {
  if (!selectedId.value) { detail.value = null; return; }
  loading.value = true; error.value = null; dirty.value = false;
  try {
    detail.value = await groupsApi.get(selectedId.value);
    editName.value = detail.value.name;
    editDescription.value = detail.value.description || '';
    editDepartment.value = detail.value.department || '';
    levels.value = permissionsToLevels(detail.value.permissions.map(p => p.code));
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 'Ошибка загрузки группы';
  } finally {
    loading.value = false;
  }
}
onMounted(loadGroups);
watch(selectedId, loadDetail);

function selectGroup(id: string) {
  if (dirty.value && !confirm('Есть несохранённые изменения. Перейти к другой группе?')) return;
  selectedId.value = id;
}
function onLevelChange(newLevels: Record<string, AccessLevel>) {
  levels.value = newLevels;
  dirty.value = true;
}

async function save() {
  if (!detail.value || !selectedId.value) return;
  saving.value = true; error.value = null;
  try {
    if (editName.value !== detail.value.name ||
        editDescription.value !== (detail.value.description || '') ||
        editDepartment.value !== (detail.value.department || '')) {
      await groupsApi.update(selectedId.value, {
        name: editName.value,
        description: editDescription.value || undefined,
        department: editDepartment.value || undefined,
      });
    }
    const newCodes = levelsToPermissions(levels.value);
    const oldCodes = detail.value.permissions.map(p => p.code).sort().join(',');
    if (newCodes.sort().join(',') !== oldCodes) {
      await groupsApi.setPermissions(selectedId.value, newCodes);
    }
    await loadGroups();
    await loadDetail();
    dirty.value = false;
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 'Ошибка сохранения';
  } finally {
    saving.value = false;
  }
}

async function removeMember(userId: string) {
  if (!detail.value || !selectedId.value) return;
  if (!confirm('Убрать пользователя из группы?')) return;
  try {
    const newIds = detail.value.members.filter(m => m.id !== userId).map(m => m.id);
    await groupsApi.setMembers(selectedId.value, newIds);
    await loadDetail();
    await loadGroups();
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 'Ошибка';
  }
}
async function addMember(userId: string) {
  if (!detail.value || !selectedId.value) return;
  if (detail.value.members.some(m => m.id === userId)) return;
  try {
    const newIds = [...detail.value.members.map(m => m.id), userId];
    await groupsApi.setMembers(selectedId.value, newIds);
    await loadDetail();
    await loadGroups();
    showMemberPicker.value = false;
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 'Ошибка';
  }
}
async function openMemberPicker() {
  showMemberPicker.value = true;
  if (allUsers.value.length === 0) {
    try {
      const resp = await rbacV3Api.listUsers({ limit: 200, is_active: true });
      allUsers.value = resp.items;
    } catch (e: any) {
      error.value = e?.response?.data?.detail || 'Ошибка загрузки пользователей';
    }
  }
}

async function onCreate() {
  if (!newGroup.value.code.trim() || !newGroup.value.name.trim()) {
    error.value = 'Код и название обязательны';
    return;
  }
  saving.value = true;
  try {
    const created = await groupsApi.create({
      code: newGroup.value.code.trim(),
      name: newGroup.value.name.trim(),
      description: newGroup.value.description.trim() || undefined,
      department: newGroup.value.department.trim() || undefined,
    });
    showCreate.value = false;
    newGroup.value = { code: '', name: '', description: '', department: '' };
    await loadGroups();
    selectedId.value = created.id;
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 'Не удалось создать группу';
  } finally {
    saving.value = false;
  }
}

async function onDelete() {
  if (!detail.value || !selectedId.value) return;
  if (detail.value.member_count > 0) {
    alert(`Нельзя удалить группу с участниками (${detail.value.member_count} чел). Сначала уберите всех.`);
    return;
  }
  if (!confirm(`Удалить группу "${detail.value.name}"?`)) return;
  try {
    await groupsApi.remove(selectedId.value);
    selectedId.value = null;
    detail.value = null;
    await loadGroups();
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 'Не удалось удалить группу';
  }
}

const availableMembers = computed(() => {
  if (!detail.value) return [];
  const existing = new Set(detail.value.members.map(m => m.id));
  return allUsers.value.filter(u =>
    !existing.has(u.id) &&
    (!memberSearch.value.trim() ||
      (u.full_name + ' ' + u.email).toLowerCase().includes(memberSearch.value.trim().toLowerCase()))
  );
});

const byDept = computed(() => {
  const map = new Map<string, RbacV3Group[]>();
  for (const g of groups.value) {
    const key = g.department || 'Без отдела';
    if (!map.has(key)) map.set(key, []);
    map.get(key)!.push(g);
  }
  return Array.from(map.entries()).sort((a, b) => a[0].localeCompare(b[0]));
});
</script>

<template>
  <div class="rv3-groups-shell">
    <!-- LEFT -->
    <div class="rv3-gr-list">
      <div class="rv3-gr-list-hd">
        <span class="rv3-rl-section-hd">Группы · {{ groups.length }}</span>
        <button class="rv3-gr-plus" @click="showCreate = true" aria-label="add">
          <svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="8" y1="3" x2="8" y2="13"/><line x1="3" y1="8" x2="13" y2="8"/></svg>
        </button>
      </div>

      <template v-for="[dept, list] in byDept" :key="dept">
        <div class="rv3-rl-section-hd" style="padding-top:14px">{{ dept }} · {{ list.length }}</div>
        <div
          v-for="g in list"
          :key="g.id"
          :class="['rv3-rl-item', { on: selectedId === g.id }]"
          @click="selectGroup(g.id)"
        >
          <div class="rv3-gr-name">{{ g.name }}</div>
          <div class="rv3-gr-meta">{{ g.member_count }} чел · {{ g.permission_count }} разреш.</div>
        </div>
      </template>

      <div v-if="groups.length === 0" class="rv3-state">Групп пока нет</div>
    </div>

    <!-- RIGHT -->
    <div class="rv3-gr-edit">
      <div v-if="loading" class="rv3-state">Загрузка...</div>
      <div v-else-if="error" class="rv3-state rv3-err">{{ error }}</div>
      <template v-else-if="detail">
        <div class="rv3-gr-edit-hd">
          <div class="rv3-gr-edit-icon">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#534AB7" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
              <circle cx="9" cy="7" r="4"/>
              <path d="M23 21v-2a4 4 0 0 0-3-3.87"/>
              <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
            </svg>
          </div>
          <div style="flex:1;">
            <input v-model="editName" class="rv3-gr-title-input" @input="dirty = true" />
            <div class="rv3-gr-meta-row">
              <span>code: <code>{{ detail.code }}</code></span>
              <span>·</span>
              <span>{{ detail.member_count }} участников</span>
            </div>
          </div>
          <button class="rv3-save" :disabled="!dirty || saving" @click="save">
            {{ saving ? 'Сохранение...' : (dirty ? 'Сохранить' : 'Сохранено') }}
          </button>
        </div>

        <div class="rv3-edit-section">
          <div class="rv3-edit-label">Описание</div>
          <textarea
            v-model="editDescription"
            class="rv3-textarea"
            @input="dirty = true"
            placeholder="Назначение группы"
          ></textarea>
        </div>

        <div class="rv3-edit-section">
          <div class="rv3-edit-label">Отдел</div>
          <input
            v-model="editDepartment"
            class="rv3-input"
            @input="dirty = true"
            placeholder="Финансовый блок / Юр.управление / ..."
          />
        </div>

        <div class="rv3-edit-section">
          <div class="rv3-edit-label rv3-edit-label-row">
            <span>Участники · {{ detail.members.length }}</span>
            <button class="rv3-link-btn" @click="openMemberPicker">+ добавить</button>
          </div>
          <div class="rv3-members">
            <div v-for="m in detail.members" :key="m.id" class="rv3-member">
              <UserAvatar :email="m.email" :full-name="m.full_name" :size="22" />
              <span class="rv3-member-name">{{ m.full_name }}</span>
              <span class="rv3-member-x" @click="removeMember(m.id)">×</span>
            </div>
            <span v-if="detail.members.length === 0" class="rv3-empty">никого нет — добавьте через кнопку справа</span>
          </div>
        </div>

        <div class="rv3-edit-section">
          <div class="rv3-edit-label">Групповые разрешения · выдаются всем участникам</div>
          <ModuleSelectGrid
            :model-value="levels"
            :editable="true"
            :columns="4"
            @update:model-value="onLevelChange"
          />
        </div>

        <div class="rv3-edit-foot">
          <div style="flex:1"></div>
          <button class="rv3-btn rv3-btn-red" @click="onDelete">Удалить группу</button>
        </div>
      </template>
      <div v-else-if="groups.length > 0" class="rv3-state">Выберите группу слева</div>
    </div>

    <!-- Member picker modal -->
    <div v-if="showMemberPicker" class="rv3-modal-bd" @click.self="showMemberPicker = false">
      <div class="rv3-modal">
        <div class="rv3-modal-hd">Добавить участника</div>
        <input v-model="memberSearch" class="rv3-input" placeholder="Поиск по имени/email..." style="margin-bottom:10px" autofocus />
        <div class="rv3-picker-list">
          <div v-for="u in availableMembers" :key="u.id" class="rv3-picker-item" @click="addMember(u.id)">
            <UserAvatar :email="u.email" :full-name="u.full_name" :size="26" />
            <div style="flex:1;min-width:0">
              <div class="rv3-picker-name">{{ u.full_name }}</div>
              <div class="rv3-picker-email">{{ u.email }}</div>
            </div>
          </div>
          <div v-if="availableMembers.length === 0" class="rv3-empty">никого не найдено</div>
        </div>
        <div style="display:flex;justify-content:flex-end;margin-top:14px;">
          <button class="rv3-btn rv3-btn-ghost" @click="showMemberPicker = false">Закрыть</button>
        </div>
      </div>
    </div>

    <!-- Create group modal -->
    <div v-if="showCreate" class="rv3-modal-bd" @click.self="showCreate = false">
      <div class="rv3-modal">
        <div class="rv3-modal-hd">Новая группа</div>
        <div class="rv3-edit-label" style="margin-top:8px">Код (slug)</div>
        <input v-model="newGroup.code" class="rv3-input" placeholder="legal / finance / mining_team" />
        <div class="rv3-edit-label" style="margin-top:8px">Название</div>
        <input v-model="newGroup.name" class="rv3-input" placeholder="Юридический блок" />
        <div class="rv3-edit-label" style="margin-top:8px">Отдел (опционально)</div>
        <input v-model="newGroup.department" class="rv3-input" placeholder="Юр.управление" />
        <div class="rv3-edit-label" style="margin-top:8px">Описание (опционально)</div>
        <textarea v-model="newGroup.description" class="rv3-textarea" />
        <div style="display:flex;gap:8px;justify-content:flex-end;margin-top:14px;">
          <button class="rv3-btn rv3-btn-ghost" @click="showCreate = false">Отмена</button>
          <button class="rv3-save" :disabled="saving" @click="onCreate">
            {{ saving ? 'Создание...' : 'Создать' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.rv3-groups-shell {
  display: grid;
  grid-template-columns: 300px 1fr;
  gap: 1px;
  background: #E5E7EB;
  min-height: calc(100vh - 56px);
  position: relative;
}
.rv3-gr-list { background: #fff; padding: 16px 0; overflow-y: auto; }
.rv3-gr-list-hd { padding: 0 18px 12px; display: flex; align-items: center; justify-content: space-between; }
.rv3-rl-section-hd {
  padding: 0 18px 8px;
  font-size: 10px; font-weight: 500; color: #888780;
  letter-spacing: .06em; text-transform: uppercase;
}
.rv3-gr-plus {
  background: transparent; border: none; color: #534AB7;
  cursor: pointer; padding: 2px; display: flex; align-items: center;
}
.rv3-rl-item {
  padding: 10px 18px;
  border-left: 3px solid transparent;
  cursor: pointer;
}
.rv3-rl-item:hover { background: #FAFAFC; }
.rv3-rl-item.on { background: rgba(127,119,221,.06); border-left-color: #7F77DD; }
.rv3-gr-name { font-size: 13px; font-weight: 500; margin-bottom: 2px; }
.rv3-gr-meta { font-size: 10.5px; color: #888780; }

.rv3-gr-edit { background: #fff; padding: 24px 28px; overflow-y: auto; }
.rv3-gr-edit-hd { display: flex; align-items: flex-start; gap: 14px; margin-bottom: 18px; }
.rv3-gr-edit-icon {
  width: 42px; height: 42px;
  background: rgba(127,119,221,.12);
  border: 1px solid rgba(127,119,221,.3);
  border-radius: 10px;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.rv3-gr-title-input {
  font-size: 16px; font-weight: 500; letter-spacing: -.01em;
  border: none; outline: none; background: transparent;
  padding: 0; width: 100%; color: #1E2A4A;
  font-family: inherit;
}
.rv3-gr-meta-row {
  font-size: 11px; color: #888780; margin-top: 3px;
  display: flex; align-items: center; gap: 8px;
}
.rv3-gr-meta-row code {
  font-family: ui-monospace, 'SF Mono', Menlo, monospace; color: #1E2A4A;
}
.rv3-save {
  padding: 7px 14px;
  background: #1D9E75; color: #fff;
  border: none; border-radius: 8px;
  font-size: 12px; font-weight: 500;
  cursor: pointer; font-family: inherit;
}
.rv3-save:disabled { background: #E5E7EB; color: #888780; cursor: not-allowed; }
.rv3-edit-section { margin-bottom: 18px; }
.rv3-edit-label {
  font-size: 10px; font-weight: 500; color: #888780;
  letter-spacing: .06em; text-transform: uppercase;
  margin-bottom: 6px;
}
.rv3-edit-label-row { display: flex; align-items: center; justify-content: space-between; }
.rv3-input {
  width: 100%; padding: 8px 12px;
  border: 0.5px solid #E5E7EB; border-radius: 8px;
  font-size: 12px; color: #1E2A4A; outline: none;
  font-family: inherit;
}
.rv3-textarea {
  width: 100%; padding: 9px 12px;
  border: 0.5px solid #E5E7EB; border-radius: 8px;
  font-size: 12px; color: #1E2A4A; outline: none;
  resize: vertical; min-height: 48px;
  font-family: inherit;
}
.rv3-link-btn {
  background: transparent; border: none; color: #534AB7;
  font-size: 11px; font-weight: 500; cursor: pointer;
  font-family: inherit;
}
.rv3-members { display: flex; flex-wrap: wrap; gap: 8px; }
.rv3-member {
  display: flex; align-items: center; gap: 6px;
  padding: 4px 8px 4px 4px;
  background: #F9FAFB; border: 0.5px solid #E5E7EB;
  border-radius: 14px; font-size: 11px;
}
.rv3-member-name { font-weight: 500; }
.rv3-member-x {
  color: #888780; cursor: pointer; padding: 0 3px;
}
.rv3-member-x:hover { color: #E24B4A; }
.rv3-empty { font-size: 11.5px; color: #888780; font-style: italic; }
.rv3-edit-foot {
  margin-top: 24px;
  padding-top: 18px;
  border-top: 0.5px solid #E5E7EB;
  display: flex; gap: 8px; align-items: center;
}
.rv3-btn {
  padding: 7px 14px; border-radius: 8px;
  font-size: 12px; font-weight: 500;
  cursor: pointer; font-family: inherit;
}
.rv3-btn-ghost { background: transparent; border: 1px solid #E5E7EB; color: #1E2A4A; }
.rv3-btn-red { background: #fff; border: 1px solid #E24B4A; color: #E24B4A; }
.rv3-btn-red:hover { background: rgba(226,75,74,.06); }
.rv3-state { padding: 60px; text-align: center; font-size: 13px; color: #888780; }
.rv3-err { color: #E24B4A; }

.rv3-modal-bd {
  position: fixed; inset: 0; z-index: 200;
  background: rgba(15,18,40,.45); backdrop-filter: blur(8px);
  display: flex; align-items: center; justify-content: center;
  padding: 36px;
}
.rv3-modal {
  width: 480px; max-width: 100%;
  background: #fff; border-radius: 14px;
  padding: 20px;
  box-shadow: 0 24px 64px rgba(15,23,60,.18);
}
.rv3-modal-hd {
  font-size: 15px; font-weight: 500; letter-spacing: -.01em;
  margin-bottom: 14px;
}
.rv3-picker-list {
  max-height: 360px; overflow-y: auto;
  display: flex; flex-direction: column; gap: 2px;
}
.rv3-picker-item {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 11px; border-radius: 7px;
  cursor: pointer;
}
.rv3-picker-item:hover { background: #FAFAFC; }
.rv3-picker-name { font-size: 12.5px; font-weight: 500; }
.rv3-picker-email { font-size: 10.5px; color: #888780; }
</style>
'@
Write-NewFile (Join-Path $root "$fe\views\rbac-v3\GroupsPage.vue") $groupsPage "[3/3] views/rbac-v3/GroupsPage.vue" -Overwrite

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
Write-Host " p142b COMPLETE - Roles + Groups live" -ForegroundColor Green
Write-Host "===================================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Test (Ctrl+Shift+R):" -ForegroundColor Cyan
Write-Host "  ROLES tab:" -ForegroundColor White
Write-Host "    - sidebar list with system + custom roles" -ForegroundColor White
Write-Host "    - click a role -> editor opens" -ForegroundColor White
Write-Host "    - 16-module grid with editable dropdowns (admin/write/read/none)" -ForegroundColor White
Write-Host "    - quick buttons: ALL ADMIN / ALL READ / RESET" -ForegroundColor White
Write-Host "    - 'Сохранить' becomes active when something changed" -ForegroundColor White
Write-Host "    - save -> PATCH /rbac/roles/{code}/permissions" -ForegroundColor White
Write-Host "  GROUPS tab:" -ForegroundColor White
Write-Host "    - list grouped by department" -ForegroundColor White
Write-Host "    - click + button -> create group modal" -ForegroundColor White
Write-Host "    - members as chips with delete x and 'добавить' picker" -ForegroundColor White
Write-Host "    - group permissions via same 16-module grid" -ForegroundColor White
Write-Host "    - delete group (only when 0 members)" -ForegroundColor White
