# =====================================================================
# p142c-rbac-v3-bulk-invite-clone.ps1   (RBAC v3 session 3 — part 3, final)
# =====================================================================
# Adds working bulk-actions, invite flow, and clone-user.
# Uses POST /rbac/users (existing) for invite + clone.
#
# In this pack:
#   1. api/rbacV3.ts — adds createUser + generatePassword helper
#   2. InviteUserModal.vue — new component (email + name + role picker)
#   3. BulkRolePickerModal.vue — new component (add / replace / remove role)
#   4. RBACShell.vue — adds "Пригласить" button (top-right)
#   5. UsersPage.vue — wires bulk-bar actions to BulkRolePickerModal
#   6. UserDetailDrawer.vue — adds "Создать аналогичного" button in footer
#
# Impersonate-mode (preview-as-user) — needs backend POST
# /rbac/users/{id}/preview-token (not yet implemented). Scheduled for
# session 4 along with magic-link email invitation.
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
            Write-Host "    SKIP: already exists" -ForegroundColor DarkGray
            return
        }
        Copy-Item -LiteralPath $path -Destination "$path.bakP142c.$stamp" -Force
        Write-Host "    backup: $path.bakP142c.$stamp" -ForegroundColor DarkGray
    }
    Ensure-Dir (Split-Path $path -Parent)
    Write-File $path $content
    Write-Host "    OK" -ForegroundColor Green
}
function Apply-Patch($path, $oldBlock, $newBlock, $label) {
    Write-Host "[*] $label" -ForegroundColor Yellow
    if (-not (Test-Path -LiteralPath $path)) { throw "File not found: $path" }
    $src = Read-File $path
    $hasCRLF = $src.Contains("`r`n")
    $srcN = $src.Replace("`r`n", "`n")
    $oldN = $oldBlock.Replace("`r`n", "`n")
    $newN = $newBlock.Replace("`r`n", "`n")
    if ($srcN.Contains($newN) -and -not $srcN.Contains($oldN)) {
        Write-Host "    SKIP: already applied" -ForegroundColor DarkGray; return
    }
    if (-not $srcN.Contains($oldN)) { throw "Anchor NOT FOUND in $label" }
    $c = 0; $i = 0
    while (($i = $srcN.IndexOf($oldN, $i)) -ge 0) { $c++; $i += $oldN.Length }
    if ($c -gt 1) { throw "Anchor NOT UNIQUE ($c) in $label" }
    Copy-Item -LiteralPath $path -Destination "$path.bakP142c.$stamp" -Force
    Write-Host "    backup: $path.bakP142c.$stamp" -ForegroundColor DarkGray
    $patched = $srcN.Replace($oldN, $newN)
    if ($hasCRLF) { $out = $patched.Replace("`n", "`r`n") } else { $out = $patched }
    Write-File $path $out
    Write-Host "    OK" -ForegroundColor Green
}

$fe = "frontend\src"

# ───────────────────────────────────────────────────────────────────────
# [1/6] api/rbacV3.ts — add createUser + generatePassword
# ───────────────────────────────────────────────────────────────────────
$apiAddon = @'

// ─── User creation (invite / clone) ──────────────────────────────

export interface RbacV3CreateUserPayload {
  email: string;
  full_name: string;
  department?: string;
  password: string;
  must_change_password?: boolean;
  role_codes: string[];
  allowed_companies?: string[];
}

export async function createUser(payload: RbacV3CreateUserPayload): Promise<RbacV3UserDetail> {
  const { data } = await api.post<RbacV3UserDetail>('/rbac/users', payload);
  return data;
}

/**
 * Generate a random 16-char password with mixed case / digits / symbols.
 * Cryptographically secure where available (window.crypto).
 */
export function generatePassword(): string {
  const sets = [
    'ABCDEFGHJKLMNPQRSTUVWXYZ',  // uppercase (no I, O — visual confusion)
    'abcdefghjkmnpqrstuvwxyz',   // lowercase (no i, l, o)
    '23456789',                   // digits (no 0, 1)
    '!@#$%^&*?',                  // symbols
  ];
  const out: string[] = [];
  // 4 chars from each set — guarantees variety
  for (const set of sets) {
    for (let i = 0; i < 4; i++) {
      const r = (window.crypto?.getRandomValues
        ? window.crypto.getRandomValues(new Uint32Array(1))[0]
        : Math.floor(Math.random() * 0xffffffff));
      out.push(set[r % set.length]);
    }
  }
  // Shuffle
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out.join('');
}
'@

$apiPath = Join-Path $root "$fe\api\rbacV3.ts"
$apiSrc = Read-File $apiPath
if ($apiSrc.Contains('export async function createUser')) {
    Write-Host "[*] [1/6] api: createUser already added" -ForegroundColor DarkGray
} else {
    Copy-Item -LiteralPath $apiPath -Destination "$apiPath.bakP142c.$stamp" -Force
    Write-Host "[*] [1/6] api/rbacV3.ts — adding createUser + generatePassword" -ForegroundColor Yellow
    Write-File $apiPath ($apiSrc + $apiAddon)
    Write-Host "    OK" -ForegroundColor Green
}

# ───────────────────────────────────────────────────────────────────────
# [2/6] components/rbac-v3/InviteUserModal.vue
# ───────────────────────────────────────────────────────────────────────
$inviteModal = @'
<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { rolesApi, createUser, generatePassword } from '@/api/rbacV3';
import type { RbacV3Role } from '@/api/rbacV3';
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

const allRoles = ref<RbacV3Role[]>([]);
const saving = ref(false);
const error = ref<string | null>(null);
const copied = ref(false);

onMounted(async () => {
  try { allRoles.value = await rolesApi.list(); }
  catch (e: any) { error.value = e?.response?.data?.detail || 'Не удалось загрузить роли'; }
});

function regenPassword() { password.value = generatePassword(); copied.value = false; }
function copyPassword() {
  navigator.clipboard.writeText(password.value).then(() => {
    copied.value = true;
    setTimeout(() => { copied.value = false; }, 2000);
  });
}
function toggleRole(code: string) {
  const i = selectedRoles.value.indexOf(code);
  if (i >= 0) selectedRoles.value.splice(i, 1);
  else selectedRoles.value.push(code);
}

async function submit() {
  if (!email.value.trim() || !fullName.value.trim()) {
    error.value = 'Email и ФИО обязательны';
    return;
  }
  saving.value = true; error.value = null;
  try {
    const u = await createUser({
      email: email.value.trim(),
      full_name: fullName.value.trim(),
      department: department.value.trim() || undefined,
      password: password.value,
      must_change_password: mustChangePassword.value,
      role_codes: selectedRoles.value,
    });
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
  <div class="rv3-modal-bd" @click.self="emit('close')">
    <div class="rv3-modal">
      <div class="rv3-modal-hd">{{ prefill ? 'Создать аналогичного пользователя' : 'Пригласить пользователя' }}</div>

      <div class="rv3-edit-label">Email</div>
      <input v-model="email" class="rv3-input" placeholder="user@uz-assets.uz" autofocus />

      <div class="rv3-edit-label" style="margin-top:10px">ФИО</div>
      <input v-model="fullName" class="rv3-input" placeholder="Иванов Иван Иванович" />

      <div class="rv3-edit-label" style="margin-top:10px">Отдел (опционально)</div>
      <input v-model="department" class="rv3-input" placeholder="Финансовый блок" />

      <div class="rv3-edit-label" style="margin-top:10px;display:flex;align-items:center;justify-content:space-between">
        <span>Временный пароль</span>
        <div style="display:flex;gap:6px">
          <button class="rv3-mini-btn" @click="regenPassword" type="button">↻ новый</button>
          <button class="rv3-mini-btn" @click="copyPassword" type="button">
            {{ copied ? '✓ скопировано' : 'копировать' }}
          </button>
        </div>
      </div>
      <div class="rv3-pwd">
        <code>{{ password }}</code>
      </div>
      <label class="rv3-cb-row">
        <input type="checkbox" v-model="mustChangePassword" />
        <span>Требовать смену пароля при первом входе</span>
      </label>

      <div class="rv3-edit-label" style="margin-top:14px">Роли</div>
      <div class="rv3-role-picker">
        <button
          v-for="r in allRoles"
          :key="r.code"
          type="button"
          :class="['rv3-role-toggle', { on: selectedRoles.includes(r.code) }]"
          @click="toggleRole(r.code)"
        >
          <RoleChip :code="r.code" size="sm" />
          <span class="rv3-role-toggle-name">{{ r.name_ru }}</span>
        </button>
        <div v-if="allRoles.length === 0" class="rv3-empty">Загрузка ролей...</div>
      </div>

      <div v-if="error" class="rv3-form-err">{{ error }}</div>

      <div class="rv3-modal-foot">
        <button class="rv3-btn rv3-btn-ghost" @click="emit('close')" :disabled="saving">Отмена</button>
        <button class="rv3-save" :disabled="saving" @click="submit">
          {{ saving ? 'Создание...' : (prefill ? 'Создать клон' : 'Пригласить') }}
        </button>
      </div>

      <div class="rv3-modal-hint" v-if="!prefill">
        Пользователь получит email с этим паролем (или сообщите ему лично).
        Magic-link приглашения по email будут в сессии 4.
      </div>
    </div>
  </div>
</template>

<style scoped>
.rv3-modal-bd {
  position: fixed; inset: 0; z-index: 200;
  background: rgba(15,18,40,.45); backdrop-filter: blur(8px);
  display: flex; align-items: center; justify-content: center;
  padding: 36px;
}
.rv3-modal {
  width: 480px; max-width: 100%;
  background: #fff; border-radius: 14px;
  padding: 22px 24px;
  box-shadow: 0 24px 64px rgba(15,23,60,.18);
  max-height: 90vh; overflow-y: auto;
}
.rv3-modal-hd { font-size: 15px; font-weight: 500; letter-spacing: -.01em; margin-bottom: 14px; }
.rv3-edit-label {
  font-size: 10px; font-weight: 500; color: #888780;
  letter-spacing: .06em; text-transform: uppercase;
  margin-bottom: 5px;
}
.rv3-input {
  width: 100%; padding: 8px 12px;
  border: 0.5px solid #E5E7EB; border-radius: 8px;
  font-size: 12px; color: #1E2A4A; outline: none;
  font-family: inherit;
}
.rv3-pwd {
  padding: 10px 12px;
  background: #F9FAFB; border: 0.5px solid #E5E7EB; border-radius: 8px;
}
.rv3-pwd code {
  font-family: ui-monospace, 'SF Mono', Menlo, monospace;
  font-size: 13px; color: #1E2A4A; letter-spacing: .04em;
  user-select: all;
}
.rv3-mini-btn {
  background: transparent; border: none; color: #534AB7;
  font-size: 10.5px; font-weight: 500; cursor: pointer;
  font-family: inherit; padding: 1px 3px;
  letter-spacing: 0; text-transform: none;
}
.rv3-cb-row {
  display: flex; align-items: center; gap: 7px;
  margin-top: 8px;
  font-size: 11.5px; color: #1E2A4A;
  cursor: pointer;
}
.rv3-cb-row input { accent-color: #7F77DD; }

.rv3-role-picker { display: flex; flex-wrap: wrap; gap: 6px; }
.rv3-role-toggle {
  display: flex; align-items: center; gap: 7px;
  padding: 5px 10px;
  background: #F9FAFB; border: 1px solid #E5E7EB; border-radius: 14px;
  cursor: pointer; font-family: inherit; font-size: 11px;
}
.rv3-role-toggle:hover { background: #fff; border-color: #D1D5DB; }
.rv3-role-toggle.on {
  background: rgba(127,119,221,.08);
  border-color: rgba(127,119,221,.4);
}
.rv3-role-toggle-name { color: #1E2A4A; }
.rv3-empty { font-size: 11.5px; color: #888780; font-style: italic; }

.rv3-form-err {
  margin-top: 12px;
  padding: 8px 11px;
  background: rgba(226,75,74,.08); border: 0.5px solid rgba(226,75,74,.3);
  border-radius: 7px;
  font-size: 11.5px; color: #A82C2B;
}
.rv3-modal-foot {
  display: flex; gap: 8px; justify-content: flex-end;
  margin-top: 16px;
}
.rv3-btn {
  padding: 7px 14px; border-radius: 8px;
  font-size: 12px; font-weight: 500;
  cursor: pointer; font-family: inherit;
}
.rv3-btn-ghost { background: transparent; border: 1px solid #E5E7EB; color: #1E2A4A; }
.rv3-save {
  padding: 7px 14px;
  background: #1D9E75; color: #fff; border: none; border-radius: 8px;
  font-size: 12px; font-weight: 500; cursor: pointer; font-family: inherit;
}
.rv3-save:disabled { background: #E5E7EB; color: #888780; cursor: not-allowed; }
.rv3-modal-hint {
  margin-top: 12px;
  padding: 8px 11px;
  background: #FAFAFC; border-radius: 7px;
  font-size: 10.5px; color: #888780; line-height: 1.5;
}
</style>
'@
Write-NewFile (Join-Path $root "$fe\components\rbac-v3\InviteUserModal.vue") $inviteModal "[2/6] InviteUserModal.vue"

# ───────────────────────────────────────────────────────────────────────
# [3/6] components/rbac-v3/BulkRolePickerModal.vue
# ───────────────────────────────────────────────────────────────────────
$bulkModal = @'
<script setup lang="ts">
import { ref, onMounted, computed } from 'vue';
import { rolesApi, rbacV3Api } from '@/api/rbacV3';
import type { RbacV3Role } from '@/api/rbacV3';
import RoleChip from './RoleChip.vue';

const props = defineProps<{ selectedIds: string[] }>();
const emit = defineEmits<{ (e: 'close'): void; (e: 'done'): void }>();

type Mode = 'add' | 'replace' | 'remove';
const mode = ref<Mode>('add');
const allRoles = ref<RbacV3Role[]>([]);
const chosenRole = ref<string | null>(null);
const progress = ref<{ done: number; total: number; failed: string[] }>({ done: 0, total: 0, failed: [] });
const applying = ref(false);

onMounted(async () => {
  try { allRoles.value = await rolesApi.list(); }
  catch (e) { console.error(e); }
});

const modeLabel = computed(() => {
  if (mode.value === 'add') return 'Добавить роль ' + props.selectedIds.length + ' пользователям';
  if (mode.value === 'replace') return 'Заменить все роли на одну у ' + props.selectedIds.length + ' пользователей';
  return 'Убрать роль у ' + props.selectedIds.length + ' пользователей';
});

async function apply() {
  if (!chosenRole.value) return;
  applying.value = true;
  progress.value = { done: 0, total: props.selectedIds.length, failed: [] };
  for (const uid of props.selectedIds) {
    try {
      const detail = await rbacV3Api.getUser(uid);
      let next: string[];
      if (mode.value === 'add') {
        next = Array.from(new Set([...detail.role_codes, chosenRole.value!]));
      } else if (mode.value === 'replace') {
        next = [chosenRole.value!];
      } else {
        next = detail.role_codes.filter(r => r !== chosenRole.value);
      }
      await rbacV3Api.update(uid, { role_codes: next });
    } catch (e: any) {
      progress.value.failed.push(uid);
    } finally {
      progress.value.done++;
    }
  }
  applying.value = false;
}

function done() { emit('done'); emit('close'); }
</script>

<template>
  <div class="rv3-modal-bd" @click.self="emit('close')">
    <div class="rv3-modal">
      <div class="rv3-modal-hd">{{ modeLabel }}</div>

      <!-- Mode selector -->
      <div class="rv3-edit-label">Действие</div>
      <div class="rv3-mode-row">
        <button :class="['rv3-mode-btn', { on: mode === 'add' }]" @click="mode = 'add'" :disabled="applying">+ Добавить роль</button>
        <button :class="['rv3-mode-btn', { on: mode === 'replace' }]" @click="mode = 'replace'" :disabled="applying">↻ Заменить все роли</button>
        <button :class="['rv3-mode-btn', { on: mode === 'remove' }]" @click="mode = 'remove'" :disabled="applying">− Убрать роль</button>
      </div>

      <div class="rv3-edit-label" style="margin-top:14px">Роль</div>
      <div class="rv3-role-picker">
        <button
          v-for="r in allRoles"
          :key="r.code"
          type="button"
          :class="['rv3-role-toggle', { on: chosenRole === r.code }]"
          :disabled="applying"
          @click="chosenRole = r.code"
        >
          <RoleChip :code="r.code" size="sm" />
          <span class="rv3-role-toggle-name">{{ r.name_ru }}</span>
        </button>
      </div>

      <!-- Progress -->
      <div v-if="applying || (progress.done > 0 && !applying)" class="rv3-progress">
        <div class="rv3-progress-bar">
          <div class="rv3-progress-fill" :style="{ width: (progress.done / progress.total * 100) + '%' }"></div>
        </div>
        <div class="rv3-progress-text">
          {{ progress.done }} / {{ progress.total }}
          <span v-if="progress.failed.length > 0" style="color:#E24B4A">· ошибок: {{ progress.failed.length }}</span>
        </div>
      </div>

      <div class="rv3-modal-foot">
        <button class="rv3-btn rv3-btn-ghost" @click="emit('close')" :disabled="applying">
          {{ progress.done > 0 && !applying ? 'Закрыть' : 'Отмена' }}
        </button>
        <button
          v-if="!(progress.done > 0 && !applying)"
          class="rv3-save"
          :disabled="!chosenRole || applying"
          @click="apply"
        >{{ applying ? 'Применение...' : 'Применить' }}</button>
        <button
          v-if="progress.done > 0 && !applying"
          class="rv3-save"
          @click="done"
        >Готово</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.rv3-modal-bd {
  position: fixed; inset: 0; z-index: 200;
  background: rgba(15,18,40,.45); backdrop-filter: blur(8px);
  display: flex; align-items: center; justify-content: center;
  padding: 36px;
}
.rv3-modal {
  width: 520px; max-width: 100%;
  background: #fff; border-radius: 14px;
  padding: 22px 24px;
  box-shadow: 0 24px 64px rgba(15,23,60,.18);
}
.rv3-modal-hd { font-size: 14px; font-weight: 500; letter-spacing: -.01em; margin-bottom: 14px; }
.rv3-edit-label {
  font-size: 10px; font-weight: 500; color: #888780;
  letter-spacing: .06em; text-transform: uppercase; margin-bottom: 6px;
}
.rv3-mode-row { display: flex; gap: 6px; }
.rv3-mode-btn {
  flex: 1;
  padding: 8px 11px;
  background: #F9FAFB; border: 1px solid #E5E7EB; border-radius: 8px;
  font-size: 11px; font-weight: 500; color: #1E2A4A;
  cursor: pointer; font-family: inherit;
}
.rv3-mode-btn:hover:not(:disabled) { border-color: #D1D5DB; }
.rv3-mode-btn.on { background: rgba(127,119,221,.08); border-color: rgba(127,119,221,.4); color: #534AB7; }
.rv3-mode-btn:disabled { opacity: .55; cursor: not-allowed; }
.rv3-role-picker { display: flex; flex-wrap: wrap; gap: 6px; }
.rv3-role-toggle {
  display: flex; align-items: center; gap: 7px;
  padding: 5px 10px;
  background: #F9FAFB; border: 1px solid #E5E7EB; border-radius: 14px;
  cursor: pointer; font-family: inherit; font-size: 11px;
}
.rv3-role-toggle:hover:not(:disabled) { background: #fff; border-color: #D1D5DB; }
.rv3-role-toggle.on { background: rgba(127,119,221,.08); border-color: rgba(127,119,221,.4); }
.rv3-role-toggle:disabled { opacity: .55; cursor: not-allowed; }
.rv3-role-toggle-name { color: #1E2A4A; }
.rv3-progress { margin-top: 14px; }
.rv3-progress-bar {
  height: 6px; background: #F3F4F8; border-radius: 3px; overflow: hidden;
}
.rv3-progress-fill {
  height: 100%; background: #1D9E75; transition: width .15s;
}
.rv3-progress-text { margin-top: 6px; font-size: 11px; color: #888780; }
.rv3-modal-foot {
  display: flex; gap: 8px; justify-content: flex-end;
  margin-top: 16px;
}
.rv3-btn {
  padding: 7px 14px; border-radius: 8px;
  font-size: 12px; font-weight: 500;
  cursor: pointer; font-family: inherit;
}
.rv3-btn-ghost { background: transparent; border: 1px solid #E5E7EB; color: #1E2A4A; }
.rv3-save {
  padding: 7px 14px;
  background: #1D9E75; color: #fff; border: none; border-radius: 8px;
  font-size: 12px; font-weight: 500; cursor: pointer; font-family: inherit;
}
.rv3-save:disabled { background: #E5E7EB; color: #888780; cursor: not-allowed; }
</style>
'@
Write-NewFile (Join-Path $root "$fe\components\rbac-v3\BulkRolePickerModal.vue") $bulkModal "[3/6] BulkRolePickerModal.vue"

# ───────────────────────────────────────────────────────────────────────
# [4/6] RBACShell.vue — add "Пригласить" button in top-right
# ───────────────────────────────────────────────────────────────────────
$oldShell = @'
const TABS = [
  { name: 'rbac-v3-users',  label: 'Пользователи' },
  { name: 'rbac-v3-roles',  label: 'Роли' },
  { name: 'rbac-v3-groups', label: 'Группы' },
  { name: 'rbac-v3-email',  label: 'Email-правила' },
  { name: 'rbac-v3-audit',  label: 'Аудит' },
];
const activeTab = computed(() => route.name as string);
function goTab(name: string) { router.push({ name }); }
</script>
'@
$newShell = @'
const TABS = [
  { name: 'rbac-v3-users',  label: 'Пользователи' },
  { name: 'rbac-v3-roles',  label: 'Роли' },
  { name: 'rbac-v3-groups', label: 'Группы' },
  { name: 'rbac-v3-email',  label: 'Email-правила' },
  { name: 'rbac-v3-audit',  label: 'Аудит' },
];
const activeTab = computed(() => route.name as string);
function goTab(name: string) { router.push({ name }); }

import { ref as _ref } from 'vue';
import InviteUserModal from '@/components/rbac-v3/InviteUserModal.vue';
const showInvite = _ref(false);
function onUserCreated(userId: string) {
  // Notify UsersPage to refresh
  window.dispatchEvent(new CustomEvent('rbac-v3:users-changed', { detail: { id: userId } }));
}
</script>
'@
Apply-Patch (Join-Path $root "$fe\views\rbac-v3\RBACShell.vue") $oldShell $newShell "[4a/6] RBACShell.vue: import InviteUserModal"

$oldShellTpl = @'
      <div class="rv3-tb-r">
        <span class="rv3-new-badge">NEW</span>
      </div>
'@
$newShellTpl = @'
      <div class="rv3-tb-r">
        <button
          v-if="activeTab === 'rbac-v3-users'"
          class="rv3-invite-btn"
          @click="showInvite = true"
          aria-label="invite"
        >
          <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="8" y1="3" x2="8" y2="13"/><line x1="3" y1="8" x2="13" y2="8"/></svg>
          Пригласить
        </button>
        <span class="rv3-new-badge">NEW</span>
      </div>
'@
Apply-Patch (Join-Path $root "$fe\views\rbac-v3\RBACShell.vue") $oldShellTpl $newShellTpl "[4b/6] RBACShell.vue: Пригласить button"

$oldShellEnd = @'
    <div class="rv3-content">
      <router-view />
    </div>
  </div>
</template>
'@
$newShellEnd = @'
    <div class="rv3-content">
      <router-view />
    </div>
    <InviteUserModal
      v-if="showInvite"
      @close="showInvite = false"
      @created="onUserCreated"
    />
  </div>
</template>
'@
Apply-Patch (Join-Path $root "$fe\views\rbac-v3\RBACShell.vue") $oldShellEnd $newShellEnd "[4c/6] RBACShell.vue: InviteModal mount"

# Add CSS for invite button
$oldShellCss = '.rv3-new-badge {
  padding: 2px 7px;'
$newShellCss = '.rv3-invite-btn {
  display: flex; align-items: center; gap: 6px;
  height: 32px; padding: 0 14px;
  background: #1D9E75; border: none; border-radius: 8px;
  color: #fff; font-size: 12px; font-weight: 500;
  cursor: pointer; font-family: inherit;
  transition: background .12s;
}
.rv3-invite-btn:hover { background: #178760; }
.rv3-new-badge {
  padding: 2px 7px;'
Apply-Patch (Join-Path $root "$fe\views\rbac-v3\RBACShell.vue") $oldShellCss $newShellCss "[4d/6] RBACShell.vue: invite button CSS"

# ───────────────────────────────────────────────────────────────────────
# [5/6] UsersPage.vue — wire bulk-bar to BulkRolePickerModal + listen to users-changed
# ───────────────────────────────────────────────────────────────────────
$oldUP = @'
import UsersPage from './UsersPage.vue';
'@
# (not present — UsersPage is self-contained)

# Patch imports
$oldImp = @'
import UserAvatar from '@/components/rbac-v3/UserAvatar.vue';
import RoleChip from '@/components/rbac-v3/RoleChip.vue';
import UserDetailDrawer from './UserDetailDrawer.vue';
'@
$newImp = @'
import UserAvatar from '@/components/rbac-v3/UserAvatar.vue';
import RoleChip from '@/components/rbac-v3/RoleChip.vue';
import UserDetailDrawer from './UserDetailDrawer.vue';
import BulkRolePickerModal from '@/components/rbac-v3/BulkRolePickerModal.vue';
'@
Apply-Patch (Join-Path $root "$fe\views\rbac-v3\UsersPage.vue") $oldImp $newImp "[5a/6] UsersPage.vue: import BulkRolePickerModal"

# Add bulk state + listener
$oldOnMount = @'
onMounted(loadUsers);
'@
$newOnMount = @'
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
'@
Apply-Patch (Join-Path $root "$fe\views\rbac-v3\UsersPage.vue") $oldOnMount $newOnMount "[5b/6] UsersPage.vue: bulk state + refresh listener"

# Wire the "Назначить роль" button (was placeholder)
$oldBulkBtn = @'
        <button class="rv3-bulk-btn">Назначить роль</button>
        <button class="rv3-bulk-x" @click="selectedIds = new Set()">✕</button>
'@
$newBulkBtn = @'
        <button class="rv3-bulk-btn" @click="showBulk = true">Назначить роль</button>
        <button class="rv3-bulk-x" @click="selectedIds = new Set()">✕</button>
'@
Apply-Patch (Join-Path $root "$fe\views\rbac-v3\UsersPage.vue") $oldBulkBtn $newBulkBtn "[5c/6] UsersPage.vue: wire 'Назначить роль' button"

# Add modal at template root
$oldDrawer = @'
    <UserDetailDrawer
      :user="selectedUser"
      @close="closeDrawer"
      @changed="onUserChanged"
    />
  </div>
</template>
'@
$newDrawer = @'
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
'@
Apply-Patch (Join-Path $root "$fe\views\rbac-v3\UsersPage.vue") $oldDrawer $newDrawer "[5d/6] UsersPage.vue: mount BulkRolePickerModal"

# ───────────────────────────────────────────────────────────────────────
# [6/6] UserDetailDrawer.vue — add "Создать аналогичного" button
# ───────────────────────────────────────────────────────────────────────
$oldDrawerImp = @'
import ModuleSelectGrid from '@/components/rbac-v3/ModuleSelectGrid.vue';
'@
$newDrawerImp = @'
import ModuleSelectGrid from '@/components/rbac-v3/ModuleSelectGrid.vue';
import InviteUserModal from '@/components/rbac-v3/InviteUserModal.vue';
'@
Apply-Patch (Join-Path $root "$fe\views\rbac-v3\UserDetailDrawer.vue") $oldDrawerImp $newDrawerImp "[6a/6] UserDetailDrawer.vue: import InviteUserModal"

$oldCloneState = @'
async function onDeactivate() {
'@
$newCloneState = @'
const showClone = ref(false);
function onCloneCreated(newId: string) {
  emit('changed');
  showClone.value = false;
  emit('open-user', newId);
}
async function onDeactivate() {
'@
Apply-Patch (Join-Path $root "$fe\views\rbac-v3\UserDetailDrawer.vue") $oldCloneState $newCloneState "[6b/6] UserDetailDrawer.vue: clone state"

# Replace footer to include clone button
$oldDrawerFoot = @'
      <!-- Footer actions -->
      <div class="rv3-dr-foot" v-if="!detail.is_owner">
        <div style="flex:1;"></div>
        <button class="rv3-btn rv3-btn-ghost" @click="onDeactivate" v-if="detail.is_active">Деактивировать</button>
        <button class="rv3-btn rv3-btn-red" @click="onDeletePermanent">Удалить</button>
      </div>
    </template>
  </div>
</template>
'@
$newDrawerFoot = @'
      <!-- Footer actions -->
      <div class="rv3-dr-foot" v-if="!detail.is_owner">
        <button class="rv3-btn rv3-btn-purple" @click="showClone = true">Создать аналогичного</button>
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
'@
Apply-Patch (Join-Path $root "$fe\views\rbac-v3\UserDetailDrawer.vue") $oldDrawerFoot $newDrawerFoot "[6c/6] UserDetailDrawer.vue: clone button + modal"

# Add purple button style
$oldBtnCss = '.rv3-btn-ghost {
  background: transparent; border: 1px solid #E5E7EB; color: #1E2A4A;
}'
$newBtnCss = '.rv3-btn-purple {
  background: #534AB7; border: none; color: #fff;
}
.rv3-btn-purple:hover { background: #463E9F; }
.rv3-btn-ghost {
  background: transparent; border: 1px solid #E5E7EB; color: #1E2A4A;
}'
Apply-Patch (Join-Path $root "$fe\views\rbac-v3\UserDetailDrawer.vue") $oldBtnCss $newBtnCss "[6d/6] UserDetailDrawer.vue: purple button CSS"

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
    docker exec -e NODE_OPTIONS=--max-old-space-size=4096 -e VITE_API_BASE_URL= $fec npx vite build 2>&1 | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "vite build failed" }
    docker restart $fec | Out-Null
    Write-Host "    restarted" -ForegroundColor Green
}

Write-Host ""
Write-Host "===================================================================" -ForegroundColor Green
Write-Host " p142c COMPLETE - Session 3 finished" -ForegroundColor Green
Write-Host "===================================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Test (Ctrl+Shift+R):" -ForegroundColor Cyan
Write-Host "  1. Topbar shows green 'Пригласить' button on Пользователи tab" -ForegroundColor White
Write-Host "  2. Click 'Пригласить' -> modal with email/name/role-toggle" -ForegroundColor White
Write-Host "     - auto-password generated (regen / copy buttons)" -ForegroundColor White
Write-Host "     - select roles via chip toggles" -ForegroundColor White
Write-Host "     - Создать = POST /rbac/users, user appears in list" -ForegroundColor White
Write-Host "  3. Check 2-3 users -> bulk-bar appears" -ForegroundColor White
Write-Host "     - 'Назначить роль' opens BulkRolePickerModal" -ForegroundColor White
Write-Host "     - 3 modes: Добавить / Заменить / Убрать" -ForegroundColor White
Write-Host "     - progress bar during apply" -ForegroundColor White
Write-Host "  4. Open user drawer -> 'Создать аналогичного' (purple, left)" -ForegroundColor White
Write-Host "     - opens invite modal prefilled with department + roles" -ForegroundColor White
Write-Host "     - new user auto-opens after create" -ForegroundColor White
Write-Host ""
Write-Host "Session 4 next: Email-rules + Audit feed + backend POST/DELETE" -ForegroundColor DarkGray
Write-Host "  roles + impersonate-token + cleanup of /admin/rbac-v2 legacy" -ForegroundColor DarkGray
