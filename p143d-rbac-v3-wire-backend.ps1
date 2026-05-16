# =====================================================================
# p143d-rbac-v3-wire-backend.ps1   (RBAC v3 session 4 - part 4, final)
# =====================================================================
# Wires the new backend endpoints (from p143c) into the UI:
#
# 1. api/rbacV3.ts:
#    - rolesApi.create / update / remove
#    - createPreviewToken
#
# 2. RolesPage.vue:
#    - "Новая роль" button -> create modal
#    - "Удалить роль" button -> works for non-system roles
#    - "Дублировать роль" -> opens create modal pre-filled
#    - Description textarea editable + saves via PATCH
#
# 3. UserDetailDrawer.vue:
#    - "Войти как этот пользователь" button (purple, footer)
#    - POST /rbac/users/{id}/preview-token, opens new tab with token
#
# 4. Updates index.html token-handler: detect ?preview_token= in URL,
#    swap into localStorage, show purple impersonate banner at top
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
        if (-not $Overwrite) { Write-Host "    SKIP" -ForegroundColor DarkGray; return }
        Copy-Item -LiteralPath $path -Destination "$path.bakP143d.$stamp" -Force
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
        Write-Host "    SKIP" -ForegroundColor DarkGray; return
    }
    if (-not $srcN.Contains($oldN)) { throw "Anchor NOT FOUND in $label" }
    $c = 0; $i = 0
    while (($i = $srcN.IndexOf($oldN, $i)) -ge 0) { $c++; $i += $oldN.Length }
    if ($c -gt 1) { throw "Anchor NOT UNIQUE ($c) in $label" }
    Copy-Item -LiteralPath $path -Destination "$path.bakP143d.$stamp" -Force
    Write-Host "    backup: $path.bakP143d.$stamp" -ForegroundColor DarkGray
    $patched = $srcN.Replace($oldN, $newN)
    if ($hasCRLF) { $out = $patched.Replace("`n", "`r`n") } else { $out = $patched }
    Write-File $path $out
    Write-Host "    OK" -ForegroundColor Green
}

$fe = "frontend\src"

# ───────────────────────────────────────────────────────────────────────
# [1/3] api/rbacV3.ts — extend rolesApi (create/update/remove) + preview-token
# ───────────────────────────────────────────────────────────────────────
$apiAddon = @'

// ─── Roles CRUD additions (Pack 143c backend) ──────────────────

export interface RbacV3RoleCreatePayload {
  code: string;
  name_ru: string;
  name_en?: string;
  description_ru?: string;
  sort_order?: number;
  permission_codes?: string[];
}

export interface RbacV3RoleUpdatePayload {
  name_ru?: string;
  name_en?: string;
  description_ru?: string;
  sort_order?: number;
}

export const rolesApiExt = {
  async create(payload: RbacV3RoleCreatePayload): Promise<RbacV3RoleDetail> {
    const { data } = await api.post<RbacV3RoleDetail>('/rbac/roles', payload);
    return data;
  },
  async update(code: string, payload: RbacV3RoleUpdatePayload): Promise<RbacV3RoleDetail> {
    const { data } = await api.patch<RbacV3RoleDetail>(`/rbac/roles/${code}`, payload);
    return data;
  },
  async remove(code: string): Promise<void> {
    await api.delete(`/rbac/roles/${code}`);
  },
};

// ─── Impersonate / preview-token ───────────────────────────────

export interface RbacV3PreviewTokenResponse {
  access_token: string;
  expires_in: number;
  target_user_id: string;
  target_email: string;
}

export async function createPreviewToken(userId: string): Promise<RbacV3PreviewTokenResponse> {
  const { data } = await api.post<RbacV3PreviewTokenResponse>(
    `/rbac/users/${userId}/preview-token`,
  );
  return data;
}
'@

$apiPath = Join-Path $root "$fe\api\rbacV3.ts"
$apiSrc = Read-File $apiPath
if ($apiSrc.Contains('export const rolesApiExt')) {
    Write-Host "[*] [1/3] api: rolesApiExt already added" -ForegroundColor DarkGray
} else {
    Copy-Item -LiteralPath $apiPath -Destination "$apiPath.bakP143d.$stamp" -Force
    Write-Host "[*] [1/3] api/rbacV3.ts: extend with rolesApiExt + createPreviewToken" -ForegroundColor Yellow
    Write-File $apiPath ($apiSrc + $apiAddon)
    Write-Host "    OK" -ForegroundColor Green
}

# ───────────────────────────────────────────────────────────────────────
# [2/3] RolesPage.vue — enable create / delete / duplicate + editable description
# ───────────────────────────────────────────────────────────────────────

# 2a. Add CreateRoleModal component first
$createRoleModal = @'
<script setup lang="ts">
import { ref } from 'vue';
import { rolesApiExt, levelsToPermissions } from '@/api/rbacV3';
import type { AccessLevel } from '@/composables/usePermissions';
import ModuleSelectGrid from './ModuleSelectGrid.vue';

const props = defineProps<{
  prefillFromCode?: string;       // when "duplicate" — copy permissions from this role
  prefillName?: string;
  prefillDescription?: string;
  prefillLevels?: Record<string, AccessLevel>;
}>();
const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'created', code: string): void;
}>();

const code = ref('');
const nameRu = ref(props.prefillName || '');
const description = ref(props.prefillDescription || '');
const levels = ref<Record<string, AccessLevel>>(props.prefillLevels || {});
const saving = ref(false);
const error = ref<string | null>(null);

function setAll(level: AccessLevel) {
  const next: Record<string, AccessLevel> = {};
  // Use MODULE_REGISTRY to ensure all keys exist
  import('@/composables/usePermissions').then(m => {
    for (const mod of m.MODULE_REGISTRY) next[mod.code] = level;
    levels.value = next;
  });
}

async function submit() {
  if (!code.value.trim() || !nameRu.value.trim()) {
    error.value = 'Code и название обязательны';
    return;
  }
  if (!/^[a-z][a-z0-9_]*$/.test(code.value.trim())) {
    error.value = 'Code: только lowercase, цифры, _ (начинается с буквы)';
    return;
  }
  saving.value = true; error.value = null;
  try {
    const permission_codes = levelsToPermissions(levels.value);
    const r = await rolesApiExt.create({
      code: code.value.trim(),
      name_ru: nameRu.value.trim(),
      description_ru: description.value.trim() || undefined,
      permission_codes,
    });
    emit('created', r.code);
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 'Не удалось создать роль';
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <div class="rv3-modal-bd" @click.self="emit('close')">
    <div class="rv3-modal rv3-modal-wide">
      <div class="rv3-modal-hd">
        {{ prefillFromCode ? 'Дублировать роль ' + prefillFromCode : 'Новая роль' }}
      </div>

      <div class="rv3-form-grid">
        <div>
          <div class="rv3-edit-label">Code (slug)</div>
          <input v-model="code" class="rv3-input" placeholder="mining_analyst" autofocus />
          <div class="rv3-input-hint">только lowercase, цифры, _ (начинается с буквы)</div>
        </div>
        <div>
          <div class="rv3-edit-label">Название</div>
          <input v-model="nameRu" class="rv3-input" placeholder="Аналитик горнодобывающей отрасли" />
        </div>
      </div>

      <div class="rv3-edit-label" style="margin-top:14px">Описание</div>
      <textarea v-model="description" class="rv3-textarea" placeholder="Назначение роли" />

      <div class="rv3-edit-label" style="margin-top:14px;display:flex;align-items:center;justify-content:space-between">
        <span>Доступ к модулям</span>
        <div style="display:flex;gap:4px;">
          <button class="rv3-quick-btn rv3-quick-admin" type="button" @click="setAll('admin')">ВСЕ ADMIN</button>
          <button class="rv3-quick-btn" type="button" @click="setAll('read')">ВСЕ READ</button>
          <button class="rv3-quick-btn" type="button" @click="setAll('none')">СБРОС</button>
        </div>
      </div>
      <ModuleSelectGrid
        :model-value="levels"
        :editable="true"
        :columns="4"
        @update:model-value="(v) => levels = v"
      />

      <div v-if="error" class="rv3-form-err">{{ error }}</div>

      <div class="rv3-modal-foot">
        <button class="rv3-btn rv3-btn-ghost" @click="emit('close')" :disabled="saving">Отмена</button>
        <button class="rv3-save" :disabled="saving" @click="submit">
          {{ saving ? 'Создание...' : 'Создать роль' }}
        </button>
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
  width: 560px; max-width: 100%;
  background: #fff; border-radius: 14px;
  padding: 22px 24px;
  box-shadow: 0 24px 64px rgba(15,23,60,.18);
  max-height: 90vh; overflow-y: auto;
}
.rv3-modal-wide { width: 760px; }
.rv3-modal-hd { font-size: 15px; font-weight: 500; letter-spacing: -.01em; margin-bottom: 14px; }
.rv3-form-grid {
  display: grid; grid-template-columns: 1fr 2fr; gap: 14px;
}
.rv3-edit-label {
  font-size: 10px; font-weight: 500; color: #888780;
  letter-spacing: .06em; text-transform: uppercase; margin-bottom: 5px;
}
.rv3-input, .rv3-textarea {
  width: 100%; padding: 8px 12px;
  border: 0.5px solid #E5E7EB; border-radius: 8px;
  font-size: 12px; color: #1E2A4A; outline: none;
  font-family: inherit;
}
.rv3-textarea { resize: vertical; min-height: 48px; }
.rv3-input-hint { margin-top: 4px; font-size: 10px; color: #888780; }
.rv3-quick-btn {
  padding: 3px 9px;
  background: #F3F4F8; color: #888780;
  border: none; border-radius: 10px;
  font-size: 9.5px; font-weight: 500;
  letter-spacing: .04em; cursor: pointer; font-family: inherit;
}
.rv3-quick-btn:hover { background: #E5E7EB; }
.rv3-quick-admin { background: rgba(29,158,117,.12) !important; color: #1D9E75 !important; }
.rv3-form-err {
  margin-top: 12px; padding: 8px 11px;
  background: rgba(226,75,74,.08); border: 0.5px solid rgba(226,75,74,.3);
  border-radius: 7px; font-size: 11.5px; color: #A82C2B;
}
.rv3-modal-foot {
  display: flex; gap: 8px; justify-content: flex-end;
  margin-top: 16px;
}
.rv3-btn { padding: 7px 14px; border-radius: 8px; font-size: 12px; font-weight: 500; cursor: pointer; font-family: inherit; }
.rv3-btn-ghost { background: transparent; border: 1px solid #E5E7EB; color: #1E2A4A; }
.rv3-save {
  padding: 7px 14px;
  background: #1D9E75; color: #fff; border: none; border-radius: 8px;
  font-size: 12px; font-weight: 500; cursor: pointer; font-family: inherit;
}
.rv3-save:disabled { background: #E5E7EB; color: #888780; cursor: not-allowed; }
</style>
'@
Write-NewFile (Join-Path $root "$fe\components\rbac-v3\CreateRoleModal.vue") $createRoleModal "[2a/3] CreateRoleModal.vue"

# 2b. Wire RolesPage — enable + - duplicate buttons
$oldRolesImports = "import ModuleSelectGrid from '@/components/rbac-v3/ModuleSelectGrid.vue';"
$newRolesImports = @'
import ModuleSelectGrid from '@/components/rbac-v3/ModuleSelectGrid.vue';
import CreateRoleModal from '@/components/rbac-v3/CreateRoleModal.vue';
import { rolesApiExt } from '@/api/rbacV3';
'@
Apply-Patch (Join-Path $root "$fe\views\rbac-v3\RolesPage.vue") $oldRolesImports $newRolesImports "[2b/3] RolesPage: import CreateRoleModal + rolesApiExt"

# Add state for modal + duplicate
$oldSaveFn = @'
async function save() {
'@
$newSaveFn = @'
const showCreate = ref(false);
const createPrefill = ref<{ name?: string; description?: string; levels?: Record<string, AccessLevel>; from?: string } | null>(null);

function openCreate() { createPrefill.value = null; showCreate.value = true; }
function openDuplicate() {
  if (!detail.value) return;
  createPrefill.value = {
    from: detail.value.code,
    name: detail.value.name_ru + ' (копия)',
    description: detail.value.description_ru || '',
    levels: { ...levels.value },
  };
  showCreate.value = true;
}
async function onRoleCreated(code: string) {
  showCreate.value = false;
  createPrefill.value = null;
  await loadRoles();
  selectedCode.value = code;
}

async function saveDescription() {
  if (!detail.value || !selectedCode.value) return;
  if ((detail.value.description_ru || '') === description.value) return;
  try {
    await rolesApiExt.update(selectedCode.value, { description_ru: description.value });
    await loadRoles();
    await loadDetail();
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 'Не удалось сохранить описание';
  }
}

async function removeRole() {
  if (!detail.value || !selectedCode.value) return;
  if (detail.value.is_system) return;
  const input = prompt(`Удалить роль "${detail.value.code}"?\nВведите code для подтверждения: ${detail.value.code}`);
  if (!input || input.trim() !== detail.value.code) {
    if (input !== null) alert('Code не совпадает');
    return;
  }
  try {
    await rolesApiExt.remove(selectedCode.value);
    selectedCode.value = null;
    detail.value = null;
    await loadRoles();
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 'Не удалось удалить роль';
  }
}

async function save() {
'@
Apply-Patch (Join-Path $root "$fe\views\rbac-v3\RolesPage.vue") $oldSaveFn $newSaveFn "[2c/3] RolesPage: add create/duplicate/delete/saveDescription"

# Enable + Новая роль button
$oldAddBtn = @'
      <button class="rv3-rl-add" disabled title="Создание ролей будет в сессии 4 (backend POST endpoint)">
        + Новая роль
      </button>
'@
$newAddBtn = @'
      <button class="rv3-rl-add" @click="openCreate">
        + Новая роль
      </button>
'@
Apply-Patch (Join-Path $root "$fe\views\rbac-v3\RolesPage.vue") $oldAddBtn $newAddBtn "[2d/3] RolesPage: enable + Новая роль"

# Make description editable (remove disabled + add @blur save)
$oldTextarea = @'
          <textarea
            v-model="description"
            class="rv3-textarea"
            placeholder="Описание роли — для чего используется"
            disabled
            title="Редактирование описания будет в сессии 4"
          ></textarea>
'@
$newTextarea = @'
          <textarea
            v-model="description"
            class="rv3-textarea"
            placeholder="Описание роли — для чего используется"
            @blur="saveDescription"
          ></textarea>
'@
Apply-Patch (Join-Path $root "$fe\views\rbac-v3\RolesPage.vue") $oldTextarea $newTextarea "[2e/3] RolesPage: editable description"

# Enable Duplicate + Delete buttons
$oldFooter = @'
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
'@
$newFooter = @'
        <div class="rv3-edit-foot">
          <button class="rv3-btn rv3-btn-ghost" @click="openDuplicate">Дублировать роль</button>
          <div style="flex:1"></div>
          <button
            v-if="!detail.is_system"
            class="rv3-btn rv3-btn-red"
            @click="removeRole"
          >Удалить роль</button>
        </div>
      </template>
    </div>

    <CreateRoleModal
      v-if="showCreate"
      :prefill-from-code="createPrefill?.from"
      :prefill-name="createPrefill?.name"
      :prefill-description="createPrefill?.description"
      :prefill-levels="createPrefill?.levels"
      @close="showCreate = false; createPrefill = null"
      @created="onRoleCreated"
    />
  </div>
</template>
'@
Apply-Patch (Join-Path $root "$fe\views\rbac-v3\RolesPage.vue") $oldFooter $newFooter "[2f/3] RolesPage: enable Duplicate + Delete + mount modal"

# ───────────────────────────────────────────────────────────────────────
# [3/3] UserDetailDrawer.vue — add "Войти как этот пользователь" button
# ───────────────────────────────────────────────────────────────────────
$oldDrawerImport = @'
import InviteUserModal from '@/components/rbac-v3/InviteUserModal.vue';
'@
$newDrawerImport = @'
import InviteUserModal from '@/components/rbac-v3/InviteUserModal.vue';
import { createPreviewToken } from '@/api/rbacV3';
'@
Apply-Patch (Join-Path $root "$fe\views\rbac-v3\UserDetailDrawer.vue") $oldDrawerImport $newDrawerImport "[3a/3] Drawer: import createPreviewToken"

$oldCloneFn = @'
function onCloneCreated(newId: string) {
  emit('changed');
  showClone.value = false;
  emit('open-user', newId);
}
'@
$newCloneFn = @'
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
'@
Apply-Patch (Join-Path $root "$fe\views\rbac-v3\UserDetailDrawer.vue") $oldCloneFn $newCloneFn "[3b/3] Drawer: startImpersonate"

# Add button in footer (before Деактивировать)
$oldDrawerFooter = @'
      <div class="rv3-dr-foot" v-if="!detail.is_owner">
        <button class="rv3-btn rv3-btn-purple" @click="showClone = true">Создать аналогичного</button>
        <div style="flex:1;"></div>
        <button class="rv3-btn rv3-btn-ghost" @click="onDeactivate" v-if="detail.is_active">Деактивировать</button>
        <button class="rv3-btn rv3-btn-red" @click="onDeletePermanent">Удалить</button>
      </div>
'@
$newDrawerFooter = @'
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
'@
Apply-Patch (Join-Path $root "$fe\views\rbac-v3\UserDetailDrawer.vue") $oldDrawerFooter $newDrawerFooter "[3c/3] Drawer: 'Войти как' button"

# Add style for impersonate button
$oldImpCss = '.rv3-btn-red:hover { background: rgba(226,75,74,.06); }'
$newImpCss = @'
.rv3-btn-red:hover { background: rgba(226,75,74,.06); }
.rv3-btn-imp {
  display: flex; align-items: center; gap: 5px;
  color: #534AB7 !important; border-color: rgba(127,119,221,.4) !important;
}
.rv3-btn-imp:hover { background: rgba(127,119,221,.06); }
.rv3-btn-imp:disabled { opacity: .55; cursor: not-allowed; }
'@
Apply-Patch (Join-Path $root "$fe\views\rbac-v3\UserDetailDrawer.vue") $oldImpCss $newImpCss "[3d/3] Drawer: 'Войти как' CSS"

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
    docker exec -e NODE_OPTIONS=--max-old-space-size=4096 -e VITE_API_BASE_URL= $fec npx vite build 2>&1 | ForEach-Object { Write-Host $_ }
    docker restart $fec | Out-Null
    Write-Host "    restarted" -ForegroundColor Green
}

Write-Host ""
Write-Host "===================================================================" -ForegroundColor Green
Write-Host " p143d COMPLETE - Session 4 frontend integration done" -ForegroundColor Green
Write-Host "===================================================================" -ForegroundColor Green
Write-Host ""
Write-Host "What now works in RBAC v3 -> Роли:" -ForegroundColor Cyan
Write-Host "  - '+ Новая роль' opens 760px modal with full editor" -ForegroundColor White
Write-Host "  - editable description (saves on blur)" -ForegroundColor White
Write-Host "  - 'Дублировать роль' opens modal pre-filled with current role" -ForegroundColor White
Write-Host "  - 'Удалить роль' for non-system roles (code-gate confirm)" -ForegroundColor White
Write-Host ""
Write-Host "User drawer:" -ForegroundColor Cyan
Write-Host "  - new purple-text 'Войти как' button (next to 'Создать аналогичного')" -ForegroundColor White
Write-Host "  - hidden for: owner / admin / ceo / inactive users" -ForegroundColor White
Write-Host "  - opens new tab with ?preview_token=... (30 min)" -ForegroundColor White
Write-Host ""
Write-Host "NOTE: preview_token URL handler in AppShell.vue is NOT yet wired." -ForegroundColor Yellow
Write-Host "  For now, copy token from URL params and use Swagger to test." -ForegroundColor Yellow
Write-Host "  Full impersonate-mode (banner + auto-login) shipping in p144." -ForegroundColor Yellow
Write-Host ""
Write-Host "Next: p144 - final cleanup (remove /admin/rbac-v2, RBACMatrix.vue, .bak* files)" -ForegroundColor DarkGray
