# =====================================================================
# p141-rbac-v3-skeleton.ps1   (RBAC v3 — session 2: split skeleton)
# =====================================================================
# Creates parallel /admin/rbac-v3 namespace alongside existing /rbac-v2.
# Existing rbac-v2 STAYS UNTOUCHED — final cleanup is a separate pack
# at the end of session 4 (p144-remove-rbac-legacy.ps1).
#
# Deliverables in this pack:
#   1. composables/usePermissions.ts — central permission resolver
#                                      (foundation for hide-on-no-access)
#   2. views/rbac-v3/ directory with 6 skeleton components
#   3. components/rbac-v3/ directory with 4 shared building blocks
#   4. Router: /admin/rbac-v3 with children (users, roles, email-rules, audit)
#   5. Sidebar: new entry "RBAC v3 · новое" with NEW-badge
#
# All skeletons render a placeholder card "Стр. в разработке (сессия 3-4)"
# so you can navigate between tabs and verify routing now.
# Real logic ships in session 3.
#
# Safe to run multiple times (idempotent).
# =====================================================================

$ErrorActionPreference = "Stop"
$enc = New-Object System.Text.UTF8Encoding($false)
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$root = $PSScriptRoot
if (-not $root) { $root = (Get-Location).Path }

function Read-File($p)  { return [System.IO.File]::ReadAllText($p, $enc) }
function Write-File($p, $text) { [System.IO.File]::WriteAllText($p, $text, $enc) }
function Ensure-Dir($d) {
    if (-not (Test-Path -LiteralPath $d)) {
        New-Item -ItemType Directory -Path $d -Force | Out-Null
        Write-Host "    created dir: $d" -ForegroundColor DarkGray
    }
}
function Write-NewFile($path, $content, $label) {
    Write-Host "[*] $label" -ForegroundColor Yellow
    if (Test-Path -LiteralPath $path) {
        Write-Host "    SKIP: file already exists" -ForegroundColor DarkGray
        return
    }
    Ensure-Dir (Split-Path $path -Parent)
    Write-File $path $content
    Write-Host "    OK: $path" -ForegroundColor Green
}
function Apply-Patch($path, $oldBlock, $newBlock, $label) {
    Write-Host "[*] $label" -ForegroundColor Yellow
    if (-not (Test-Path -LiteralPath $path)) { throw "File not found: $path" }
    $src = Read-File $path
    $fileHasCRLF = $src.Contains("`r`n")
    $srcN = $src.Replace("`r`n", "`n")
    $oldN = $oldBlock.Replace("`r`n", "`n")
    $newN = $newBlock.Replace("`r`n", "`n")
    if ($srcN.Contains($newN) -and -not $srcN.Contains($oldN)) {
        Write-Host "    SKIP: already applied" -ForegroundColor DarkGray
        return
    }
    if (-not $srcN.Contains($oldN)) { throw "Anchor NOT FOUND in $path ($label)" }
    $count = 0; $idx = 0
    while (($idx = $srcN.IndexOf($oldN, $idx)) -ge 0) { $count++; $idx += $oldN.Length }
    if ($count -gt 1) { throw "Anchor NOT UNIQUE ($count) in $label" }
    $bak = "$path.bakP141.$stamp"
    Copy-Item -LiteralPath $path -Destination $bak -Force
    Write-Host "    backup: $bak" -ForegroundColor DarkGray
    $patchedN = $srcN.Replace($oldN, $newN)
    if ($fileHasCRLF) { $out = $patchedN.Replace("`n", "`r`n") } else { $out = $patchedN }
    Write-File $path $out
    Write-Host "    OK" -ForegroundColor Green
}

$fe = "frontend\src"

# ───────────────────────────────────────────────────────────────────────
# [1/12] composables/usePermissions.ts — foundation for hide-on-no-access
# ───────────────────────────────────────────────────────────────────────
$usePerm = @'
/**
 * usePermissions — central permission resolver for hide-on-no-access pattern.
 *
 * Reads from auth store: user.permissions[] + user.module_visibility + roles[].
 * Returns reactive booleans for each action in a given module.
 *
 * USAGE:
 *   <script setup>
 *   import { usePermissions } from '@/composables/usePermissions';
 *   const perm = usePermissions('kpi');
 *   </script>
 *
 *   <template>
 *     <button v-if="perm.canEdit">Edit</button>
 *     <button v-if="perm.canExport">Export</button>
 *   </template>
 *
 * The "level" property gives a coarse 4-value (none / read / write / admin)
 * derived from the most permissive action available. Used by Access-карта
 * to show one chip per module.
 */
import { computed } from 'vue';
import { useAuthStore } from '@/stores/auth';

export type AccessLevel = 'none' | 'read' | 'write' | 'admin';

export interface PermissionResult {
  level: AccessLevel;
  canView: boolean;
  canEdit: boolean;
  canApprove: boolean;
  canExport: boolean;
  canDelete: boolean;
  canManage: boolean;
  explain: string;
}

function _hasCode(codes: string[], moduleCode: string, action: string): boolean {
  return codes.includes(`${moduleCode}.${action}`) ||
         codes.includes(`${moduleCode}.manage`) ||
         codes.includes('*');
}

function _computeLevel(r: { canView: boolean; canEdit: boolean; canManage: boolean }): AccessLevel {
  if (r.canManage) return 'admin';
  if (r.canEdit) return 'write';
  if (r.canView) return 'read';
  return 'none';
}

export function usePermissions(moduleCode: string) {
  const auth = useAuthStore();

  const result = computed<PermissionResult>(() => {
    const user = auth.user;
    if (!user) {
      return {
        level: 'none', canView: false, canEdit: false, canApprove: false,
        canExport: false, canDelete: false, canManage: false,
        explain: 'не авторизован',
      };
    }
    // Owner bypass — full access everywhere
    if (user.is_owner) {
      return {
        level: 'admin', canView: true, canEdit: true, canApprove: true,
        canExport: true, canDelete: true, canManage: true,
        explain: 'владелец платформы',
      };
    }
    // Extract permission codes from user.permissions (array of objects or strings)
    const perms = (user.permissions || []) as Array<string | { code: string; is_denied?: boolean }>;
    const grantedCodes: string[] = [];
    const deniedCodes: string[] = [];
    for (const p of perms) {
      if (typeof p === 'string') {
        grantedCodes.push(p);
      } else if (p && typeof p === 'object') {
        if (p.is_denied) deniedCodes.push(p.code);
        else grantedCodes.push(p.code);
      }
    }
    // Module visibility: if explicitly hidden, return 'none' regardless of permissions
    const mv = (user.module_visibility || {}) as Record<string, boolean>;
    if (mv[moduleCode] === false) {
      return {
        level: 'none', canView: false, canEdit: false, canApprove: false,
        canExport: false, canDelete: false, canManage: false,
        explain: 'модуль скрыт администратором',
      };
    }
    // Role-based bypass: admin / ceo roles get admin level on everything
    const roleCodes = (user.roles || []).map((r: any) =>
      typeof r === 'string' ? r : r.code
    );
    if (roleCodes.includes('admin') || roleCodes.includes('ceo')) {
      return {
        level: 'admin', canView: true, canEdit: true, canApprove: true,
        canExport: true, canDelete: true, canManage: true,
        explain: `via role: ${roleCodes.includes('admin') ? 'admin' : 'ceo'}`,
      };
    }
    // Compute per-action booleans
    const isDenied = (action: string) =>
      deniedCodes.includes(`${moduleCode}.${action}`);
    const canView    = !isDenied('view')   && _hasCode(grantedCodes, moduleCode, 'view');
    const canEdit    = !isDenied('edit')   && _hasCode(grantedCodes, moduleCode, 'edit');
    const canApprove = !isDenied('approve')&& _hasCode(grantedCodes, moduleCode, 'approve');
    const canExport  = !isDenied('export') && _hasCode(grantedCodes, moduleCode, 'export');
    const canDelete  = !isDenied('delete') && _hasCode(grantedCodes, moduleCode, 'delete');
    const canManage  = !isDenied('manage') && grantedCodes.includes(`${moduleCode}.manage`);
    const level = _computeLevel({ canView, canEdit, canManage });
    return {
      level, canView, canEdit, canApprove, canExport, canDelete, canManage,
      explain: level === 'none' ? 'нет в роли' : `via permissions`,
    };
  });

  return {
    level:      computed(() => result.value.level),
    canView:    computed(() => result.value.canView),
    canEdit:    computed(() => result.value.canEdit),
    canApprove: computed(() => result.value.canApprove),
    canExport:  computed(() => result.value.canExport),
    canDelete:  computed(() => result.value.canDelete),
    canManage:  computed(() => result.value.canManage),
    explain:    computed(() => result.value.explain),
  };
}

/**
 * MODULE_REGISTRY — single source of truth for the 16 modules used
 * across RBAC v3 Access-карта and Roles editor.
 */
export const MODULE_REGISTRY = [
  { code: 'dashboard',    label: 'Дашборд'           },
  { code: 'bp',           label: 'Бизнес-план'       },
  { code: 'kpi',          label: 'KPI'               },
  { code: 'financials',   label: 'Финансы (МСФО/НСБУ)' },
  { code: 'credit',       label: 'Кредитный портфель' },
  { code: 'invest',       label: 'Инвест-проекты'    },
  { code: 'procurement',  label: 'Закупки'           },
  { code: 'esg',          label: 'ESG'               },
  { code: 'governance',   label: 'Корпуправление'    },
  { code: 'ratings',      label: 'Рейтинги'          },
  { code: 'procurement_analysis', label: 'Анализ закупок' },
  { code: 'consultants',  label: 'Консультанты'      },
  { code: 'tasks',        label: 'Задачи'            },
  { code: 'reports',      label: 'Отчёты'            },
  { code: 'ai',           label: 'AI-чат'            },
  { code: 'admin',        label: 'Администрирование' },
] as const;

export type ModuleCode = typeof MODULE_REGISTRY[number]['code'];
'@
Write-NewFile (Join-Path $root "$fe\composables\usePermissions.ts") $usePerm "[1/12] composables/usePermissions.ts"

# ───────────────────────────────────────────────────────────────────────
# [2/12] components/rbac-v3/RoleChip.vue
# ───────────────────────────────────────────────────────────────────────
$roleChip = @'
<script setup lang="ts">
defineProps<{
  code: string;
  size?: 'sm' | 'md';
  removable?: boolean;
}>();
defineEmits<{ (e: 'remove'): void }>();
const COLORS: Record<string, { bg: string; fg: string }> = {
  admin:     { bg: 'rgba(226,75,74,.12)',  fg: '#A82C2B' },
  ceo:       { bg: 'rgba(239,159,39,.12)', fg: '#B27015' },
  debt:      { bg: 'rgba(29,158,117,.12)', fg: '#1D9E75' },
  readonly:  { bg: '#F3F4F8',              fg: '#888780' },
  imv_admin: { bg: 'rgba(55,138,221,.12)', fg: '#1E5AAA' },
  analyst:   { bg: 'rgba(127,119,221,.12)', fg: '#534AB7' },
};
function colorFor(code: string) {
  return COLORS[code] || { bg: 'rgba(127,119,221,.12)', fg: '#534AB7' };
}
</script>

<template>
  <span
    class="rv3-chip"
    :class="{ sm: size === 'sm' }"
    :style="{ background: colorFor(code).bg, color: colorFor(code).fg }"
  >
    {{ code }}
    <span v-if="removable" class="rv3-chip-x" @click.stop="$emit('remove')">×</span>
  </span>
</template>

<style scoped>
.rv3-chip {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 4px 10px; border-radius: 14px;
  font-size: 11px; font-weight: 500;
  white-space: nowrap;
}
.rv3-chip.sm { padding: 2px 8px; font-size: 10px; }
.rv3-chip-x {
  cursor: pointer;
  opacity: 0.6;
  font-size: 13px;
  line-height: 1;
}
.rv3-chip-x:hover { opacity: 1; }
</style>
'@
Write-NewFile (Join-Path $root "$fe\components\rbac-v3\RoleChip.vue") $roleChip "[2/12] components/rbac-v3/RoleChip.vue"

# ───────────────────────────────────────────────────────────────────────
# [3/12] components/rbac-v3/UserAvatar.vue
# ───────────────────────────────────────────────────────────────────────
$userAvatar = @'
<script setup lang="ts">
import { computed } from 'vue';
const props = defineProps<{
  email?: string;
  fullName?: string;
  size?: number;
}>();
const initials = computed(() => {
  const name = props.fullName?.trim();
  if (name) {
    const parts = name.split(/\s+/);
    if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
    return name.slice(0, 2).toUpperCase();
  }
  const email = props.email || '';
  const local = email.split('@')[0] || '';
  const parts = local.split(/[._-]/);
  if (parts.length >= 2 && parts[0] && parts[1]) return (parts[0][0] + parts[1][0]).toUpperCase();
  return local.slice(0, 2).toUpperCase() || '?';
});
const sz = computed(() => props.size || 30);
const fs = computed(() => Math.round(sz.value * 0.4));
</script>

<template>
  <div class="rv3-avatar" :style="{ width: sz + 'px', height: sz + 'px', fontSize: fs + 'px' }">
    {{ initials }}
  </div>
</template>

<style scoped>
.rv3-avatar {
  background: linear-gradient(135deg, #7F77DD, #534AB7);
  border-radius: 8px;
  color: #fff;
  font-weight: 500;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
  user-select: none;
}
</style>
'@
Write-NewFile (Join-Path $root "$fe\components\rbac-v3\UserAvatar.vue") $userAvatar "[3/12] components/rbac-v3/UserAvatar.vue"

# ───────────────────────────────────────────────────────────────────────
# [4/12] components/rbac-v3/AccessCard.vue
# ───────────────────────────────────────────────────────────────────────
$accessCard = @'
<script setup lang="ts">
import { computed } from 'vue';
import type { AccessLevel } from '@/composables/usePermissions';

const props = defineProps<{
  moduleCode: string;
  moduleLabel: string;
  level: AccessLevel;
  explain?: string;
  scope?: string;
  manualGrant?: boolean;
  editable?: boolean;
}>();
defineEmits<{ (e: 'change', level: AccessLevel): void; (e: 'click'): void }>();

const LEVEL_META: Record<AccessLevel, { color: string; bg: string; label: string }> = {
  admin: { color: '#1D9E75', bg: 'rgba(29,158,117,.12)', label: 'ADMIN' },
  write: { color: '#534AB7', bg: 'rgba(127,119,221,.12)', label: 'WRITE' },
  read:  { color: '#1E5AAA', bg: 'rgba(55,138,221,.12)',  label: 'READ' },
  none:  { color: '#888780', bg: '#F3F4F8',               label: 'NONE' },
};

const borderColor = computed(() => {
  if (props.manualGrant) return '#EF9F27';
  return LEVEL_META[props.level].color === '#888780' ? '#D1D5DB' : LEVEL_META[props.level].color;
});
const meta = computed(() => LEVEL_META[props.level]);
const dim  = computed(() => props.level === 'none' && !props.editable);
</script>

<template>
  <div
    class="rv3-card"
    :class="{ dim }"
    :style="{ borderLeftColor: borderColor }"
    @click="$emit('click')"
  >
    <div class="rv3-card-row">
      <div class="rv3-card-name">{{ moduleLabel }}</div>
      <select
        v-if="editable"
        :value="level"
        class="rv3-card-pill"
        :style="{ color: meta.color, background: meta.bg }"
        @change="$emit('change', ($event.target as HTMLSelectElement).value as AccessLevel)"
        @click.stop
      >
        <option value="admin">ADMIN</option>
        <option value="write">WRITE</option>
        <option value="read">READ</option>
        <option value="none">NONE</option>
      </select>
      <span
        v-else
        class="rv3-card-pill"
        :style="{ color: meta.color, background: meta.bg }"
      >{{ meta.label }}</span>
    </div>
    <div class="rv3-card-sub" :class="{ warn: manualGrant }">
      <template v-if="manualGrant">+ персональный grant</template>
      <template v-else>{{ explain }}{{ scope ? ' · scope: ' + scope : '' }}</template>
    </div>
  </div>
</template>

<style scoped>
.rv3-card {
  background: #FAFAFC;
  border: 0.5px solid #E5E7EB;
  border-left: 3px solid #D1D5DB;
  border-radius: 8px;
  padding: 9px 11px;
  cursor: pointer;
  transition: background 0.12s;
}
.rv3-card:hover { background: #fff; }
.rv3-card.dim { opacity: 0.55; }
.rv3-card-row {
  display: flex; align-items: flex-start; justify-content: space-between;
  gap: 8px; margin-bottom: 4px;
}
.rv3-card-name {
  font-size: 12px; font-weight: 500; color: #1E2A4A;
}
.rv3-card-pill {
  padding: 1px 7px; border-radius: 9px;
  font-size: 9.5px; font-weight: 500;
  letter-spacing: .04em;
  border: none; outline: none;
  cursor: inherit;
  font-family: inherit;
}
.rv3-card-sub {
  font-size: 10px; color: #888780;
}
.rv3-card-sub.warn { color: #B27015; font-weight: 500; }
</style>
'@
Write-NewFile (Join-Path $root "$fe\components\rbac-v3\AccessCard.vue") $accessCard "[4/12] components/rbac-v3/AccessCard.vue"

# ───────────────────────────────────────────────────────────────────────
# [5/12] components/rbac-v3/ModuleSelectGrid.vue
# ───────────────────────────────────────────────────────────────────────
$moduleGrid = @'
<script setup lang="ts">
import { MODULE_REGISTRY } from '@/composables/usePermissions';
import type { AccessLevel } from '@/composables/usePermissions';
import AccessCard from './AccessCard.vue';

defineProps<{
  /** Map of moduleCode -> level. Modules not in map default to 'none'. */
  modelValue: Record<string, AccessLevel>;
  /** If true, cards render <select> instead of static pill. */
  editable?: boolean;
  /** Source of each module's access ('via role: X' or 'manual grant'). */
  sources?: Record<string, string>;
  columns?: number;
}>();
defineEmits<{ (e: 'update:modelValue', value: Record<string, AccessLevel>): void }>();
</script>

<template>
  <div class="rv3-grid" :style="{ gridTemplateColumns: `repeat(${columns || 2}, 1fr)` }">
    <AccessCard
      v-for="m in MODULE_REGISTRY"
      :key="m.code"
      :module-code="m.code"
      :module-label="m.label"
      :level="modelValue[m.code] || 'none'"
      :explain="sources?.[m.code] || (modelValue[m.code] && modelValue[m.code] !== 'none' ? 'via permissions' : 'нет в роли')"
      :editable="editable"
      @change="(lvl) => $emit('update:modelValue', { ...modelValue, [m.code]: lvl })"
    />
  </div>
</template>

<style scoped>
.rv3-grid {
  display: grid;
  gap: 8px;
}
</style>
'@
Write-NewFile (Join-Path $root "$fe\components\rbac-v3\ModuleSelectGrid.vue") $moduleGrid "[5/12] components/rbac-v3/ModuleSelectGrid.vue"

# ───────────────────────────────────────────────────────────────────────
# [6/12] views/rbac-v3/RBACShell.vue — topbar with tabs + router-view
# ───────────────────────────────────────────────────────────────────────
$shell = @'
<script setup lang="ts">
/**
 * RBAC v3 — top-level shell. Renders topbar with 4 tab links and
 * <router-view /> for the active child route.
 */
import { computed, inject } from 'vue';
import { useRouter, useRoute } from 'vue-router';

const router = useRouter();
const route = useRoute();
const toggleSidebar = inject<() => void>('toggleSidebar', () => {});

const TABS = [
  { name: 'rbac-v3-users',  label: 'Пользователи' },
  { name: 'rbac-v3-roles',  label: 'Роли' },
  { name: 'rbac-v3-email',  label: 'Email-правила' },
  { name: 'rbac-v3-audit',  label: 'Аудит' },
];
const activeTab = computed(() => route.name as string);
function goTab(name: string) { router.push({ name }); }
</script>

<template>
  <div class="rv3-shell">
    <div class="rv3-topbar">
      <div class="rv3-tb-l">
        <button class="rv3-sb-toggle" @click="toggleSidebar()" aria-label="toggle sidebar">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
        </button>
        <div class="rv3-tabs">
          <button
            v-for="t in TABS"
            :key="t.name"
            :class="['rv3-tab', { on: activeTab === t.name }]"
            @click="goTab(t.name)"
          >{{ t.label }}</button>
        </div>
      </div>
      <div class="rv3-tb-c">
        <div class="rv3-tb-eyebrow">UzAssets · Администрирование</div>
        <div class="rv3-tb-title">Управление доступом · v3</div>
      </div>
      <div class="rv3-tb-r">
        <span class="rv3-new-badge">NEW</span>
      </div>
    </div>
    <div class="rv3-content">
      <router-view />
    </div>
  </div>
</template>

<style scoped>
.rv3-shell { display: flex; flex-direction: column; min-height: 100vh; background: #F4F3F9; }
.rv3-topbar {
  display: grid; grid-template-columns: auto 1fr auto;
  grid-template-rows: 56px;
  align-items: center; gap: 16px;
  padding: 0 24px;
  background: linear-gradient(180deg, #1E2A4A 0%, #1A2440 100%);
  color: #fff;
  border-bottom: 0.5px solid rgba(255,255,255,0.06);
  position: sticky; top: 0; z-index: 10;
}
.rv3-tb-l { display: flex; align-items: center; gap: 12px; }
.rv3-tb-c { display: flex; flex-direction: column; align-items: center; gap: 1px; min-width: 0; text-align: center; }
.rv3-tb-r { justify-self: end; display: flex; align-items: center; gap: 8px; }
.rv3-tb-eyebrow {
  font-size: 9.5px; font-weight: 500; letter-spacing: .1em;
  text-transform: uppercase; color: rgba(255,255,255,.5);
}
.rv3-tb-title { font-size: 15px; font-weight: 500; letter-spacing: -.01em; }
.rv3-sb-toggle {
  width: 32px; height: 32px;
  border: 1px solid rgba(255,255,255,.15);
  background: rgba(255,255,255,.06);
  border-radius: 8px; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  color: rgba(255,255,255,.7); transition: all .15s; padding: 0;
}
.rv3-sb-toggle:hover { background: rgba(255,255,255,.14); color: #fff; }
.rv3-tabs {
  display: flex; background: rgba(255,255,255,.06);
  border-radius: 8px; padding: 2px;
  font-size: 12px; font-weight: 500;
}
.rv3-tab {
  padding: 5px 14px; border-radius: 6px;
  background: transparent; border: none;
  color: rgba(255,255,255,.55); cursor: pointer;
  font-family: inherit; font-size: 12px; font-weight: 500;
  transition: all .15s;
}
.rv3-tab:hover { color: rgba(255,255,255,.85); }
.rv3-tab.on { background: rgba(255,255,255,.14); color: #fff; }
.rv3-new-badge {
  padding: 2px 7px;
  background: #1D9E75;
  color: #fff;
  border-radius: 8px;
  font-size: 9.5px; font-weight: 500; letter-spacing: .06em;
}
.rv3-content { flex: 1; }
</style>
'@
Write-NewFile (Join-Path $root "$fe\views\rbac-v3\RBACShell.vue") $shell "[6/12] views/rbac-v3/RBACShell.vue"

# ───────────────────────────────────────────────────────────────────────
# [7/12] views/rbac-v3/UsersPage.vue — skeleton
# ───────────────────────────────────────────────────────────────────────
$usersPage = @'
<script setup lang="ts">
/** Session 3 will fill this. For now: skeleton placeholder. */
</script>

<template>
  <div class="rv3-page">
    <div class="rv3-placeholder">
      <div class="rv3-ph-eyebrow">RBAC v3 · Сессия 3</div>
      <div class="rv3-ph-title">Пользователи</div>
      <div class="rv3-ph-text">
        Список пользователей с фильтр-чипами, bulk-actions, глобальный поиск,
        кнопка «Пригласить» и user-detail drawer с Access-картой.
        <br/><br/>
        Реализуется в следующей сессии.
      </div>
    </div>
  </div>
</template>

<style scoped>
.rv3-page { padding: 24px; }
.rv3-placeholder {
  max-width: 640px; margin: 60px auto;
  background: #fff; border: 0.5px solid #E5E7EB; border-radius: 14px;
  padding: 32px;
  box-shadow: 0 4px 16px rgba(15,23,60,.04);
  text-align: center;
}
.rv3-ph-eyebrow {
  font-size: 10px; font-weight: 500; color: #534AB7;
  letter-spacing: .08em; text-transform: uppercase; margin-bottom: 8px;
}
.rv3-ph-title {
  font-size: 18px; font-weight: 500; letter-spacing: -.01em;
  color: #1E2A4A; margin-bottom: 14px;
}
.rv3-ph-text {
  font-size: 13px; color: #888780; line-height: 1.6;
}
</style>
'@
Write-NewFile (Join-Path $root "$fe\views\rbac-v3\UsersPage.vue") $usersPage "[7/12] views/rbac-v3/UsersPage.vue"

# ───────────────────────────────────────────────────────────────────────
# [8/12] views/rbac-v3/RolesPage.vue — skeleton
# ───────────────────────────────────────────────────────────────────────
$rolesPage = @'
<script setup lang="ts">
/** Session 3 will fill this. */
</script>

<template>
  <div class="rv3-page">
    <div class="rv3-placeholder">
      <div class="rv3-ph-eyebrow">RBAC v3 · Сессия 3</div>
      <div class="rv3-ph-title">Роли</div>
      <div class="rv3-ph-text">
        Sidebar со списком ролей (системные + пользовательские),
        центральный редактор с Access-картой 16 модулей, default scope,
        возможность создать / дублировать / удалить роль.
      </div>
    </div>
  </div>
</template>

<style scoped>
.rv3-page { padding: 24px; }
.rv3-placeholder {
  max-width: 640px; margin: 60px auto;
  background: #fff; border: 0.5px solid #E5E7EB; border-radius: 14px;
  padding: 32px;
  box-shadow: 0 4px 16px rgba(15,23,60,.04);
  text-align: center;
}
.rv3-ph-eyebrow { font-size: 10px; font-weight: 500; color: #534AB7; letter-spacing: .08em; text-transform: uppercase; margin-bottom: 8px; }
.rv3-ph-title { font-size: 18px; font-weight: 500; letter-spacing: -.01em; color: #1E2A4A; margin-bottom: 14px; }
.rv3-ph-text { font-size: 13px; color: #888780; line-height: 1.6; }
</style>
'@
Write-NewFile (Join-Path $root "$fe\views\rbac-v3\RolesPage.vue") $rolesPage "[8/12] views/rbac-v3/RolesPage.vue"

# ───────────────────────────────────────────────────────────────────────
# [9/12] views/rbac-v3/EmailRulesPage.vue — skeleton
# ───────────────────────────────────────────────────────────────────────
$emailPage = @'
<script setup lang="ts">
/** Session 4 will fill this. */
</script>

<template>
  <div class="rv3-page">
    <div class="rv3-placeholder">
      <div class="rv3-ph-eyebrow">RBAC v3 · Сессия 4</div>
      <div class="rv3-ph-title">Email-правила автоназначения</div>
      <div class="rv3-ph-text">
        Правила вида: если email совпадает с pattern (например, *@uz-assets.uz)
        — автоматически выдать роль X при первом входе.
      </div>
    </div>
  </div>
</template>

<style scoped>
.rv3-page { padding: 24px; }
.rv3-placeholder { max-width: 640px; margin: 60px auto; background: #fff; border: 0.5px solid #E5E7EB; border-radius: 14px; padding: 32px; box-shadow: 0 4px 16px rgba(15,23,60,.04); text-align: center; }
.rv3-ph-eyebrow { font-size: 10px; font-weight: 500; color: #534AB7; letter-spacing: .08em; text-transform: uppercase; margin-bottom: 8px; }
.rv3-ph-title { font-size: 18px; font-weight: 500; letter-spacing: -.01em; color: #1E2A4A; margin-bottom: 14px; }
.rv3-ph-text { font-size: 13px; color: #888780; line-height: 1.6; }
</style>
'@
Write-NewFile (Join-Path $root "$fe\views\rbac-v3\EmailRulesPage.vue") $emailPage "[9/12] views/rbac-v3/EmailRulesPage.vue"

# ───────────────────────────────────────────────────────────────────────
# [10/12] views/rbac-v3/AuditFeedPage.vue — skeleton
# ───────────────────────────────────────────────────────────────────────
$auditPage = @'
<script setup lang="ts">
/** Session 4 will fill this with GitHub-style feed. */
</script>

<template>
  <div class="rv3-page">
    <div class="rv3-placeholder">
      <div class="rv3-ph-eyebrow">RBAC v3 · Сессия 4</div>
      <div class="rv3-ph-title">Журнал аудита</div>
      <div class="rv3-ph-text">
        Feed в стиле GitHub: события хронологически с avatar+severity-dot+
        человеко-читаемым описанием. Фильтры по периоду / типу / severity.
        Экспорт в CSV для compliance.
      </div>
    </div>
  </div>
</template>

<style scoped>
.rv3-page { padding: 24px; }
.rv3-placeholder { max-width: 640px; margin: 60px auto; background: #fff; border: 0.5px solid #E5E7EB; border-radius: 14px; padding: 32px; box-shadow: 0 4px 16px rgba(15,23,60,.04); text-align: center; }
.rv3-ph-eyebrow { font-size: 10px; font-weight: 500; color: #534AB7; letter-spacing: .08em; text-transform: uppercase; margin-bottom: 8px; }
.rv3-ph-title { font-size: 18px; font-weight: 500; letter-spacing: -.01em; color: #1E2A4A; margin-bottom: 14px; }
.rv3-ph-text { font-size: 13px; color: #888780; line-height: 1.6; }
</style>
'@
Write-NewFile (Join-Path $root "$fe\views\rbac-v3\AuditFeedPage.vue") $auditPage "[10/12] views/rbac-v3/AuditFeedPage.vue"

# ───────────────────────────────────────────────────────────────────────
# [11/12] router/index.ts — add /admin/rbac-v3 + children
# ───────────────────────────────────────────────────────────────────────
$oldRouter = '        // Pack 9.1: RBAC v2'
$newRouter = @'
        // Pack 141: RBAC v3 (parallel to v2 — for testing; will replace v2 in p144)
        {
          path: "admin/rbac-v3",
          component: () => import("@/views/rbac-v3/RBACShell.vue"),
          meta: { title: "RBAC v3", requiresPermission: "admin.users" },
          children: [
            { path: "", redirect: { name: "rbac-v3-users" } },
            { path: "users", name: "rbac-v3-users", component: () => import("@/views/rbac-v3/UsersPage.vue") },
            { path: "roles", name: "rbac-v3-roles", component: () => import("@/views/rbac-v3/RolesPage.vue") },
            { path: "email-rules", name: "rbac-v3-email", component: () => import("@/views/rbac-v3/EmailRulesPage.vue") },
            { path: "audit", name: "rbac-v3-audit", component: () => import("@/views/rbac-v3/AuditFeedPage.vue") },
          ],
        },
        // Pack 9.1: RBAC v2
'@
Apply-Patch (Join-Path $root "$fe\router\index.ts") $oldRouter $newRouter "[11/12] router: /admin/rbac-v3 + children"

# ───────────────────────────────────────────────────────────────────────
# [12/12] AppShell sidebar: add "RBAC v3" entry
# ───────────────────────────────────────────────────────────────────────
$oldSb = '          <!-- Pack 9.2: RBAC v2 — единая admin панель (users + groups + companies + sectors + templates) -->
          <RouterLink to="/admin/rbac-v2" class="sb-item sb-item-admin" active-class="active">'
$newSb = '          <!-- Pack 141: RBAC v3 (parallel new admin panel) -->
          <RouterLink to="/admin/rbac-v3" class="sb-item sb-item-admin" active-class="active">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M12 2l7 4v6c0 5-3.5 8.5-7 10-3.5-1.5-7-5-7-10V6z"/>
            </svg>
            <span class="sb-name">RBAC v3 · доступы</span>
            <span style="margin-left:auto;padding:1px 6px;background:#1D9E75;color:#fff;border-radius:7px;font-size:8.5px;font-weight:500;letter-spacing:.05em;">NEW</span>
          </RouterLink>

          <!-- Pack 9.2: RBAC v2 — единая admin панель (users + groups + companies + sectors + templates) -->
          <RouterLink to="/admin/rbac-v2" class="sb-item sb-item-admin" active-class="active">'
Apply-Patch (Join-Path $root "$fe\views\AppShell.vue") $oldSb $newSb "[12/12] AppShell sidebar: RBAC v3 entry"

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
Write-Host " p141 COMPLETE — RBAC v3 skeleton ready" -ForegroundColor Green
Write-Host "===================================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Test (Ctrl+Shift+R):" -ForegroundColor Cyan
Write-Host "  1. Sidebar: new 'RBAC v3 . доступы' entry (with NEW badge)" -ForegroundColor White
Write-Host "  2. Click it -> opens /admin/rbac-v3 with navy topbar + 4 tabs" -ForegroundColor White
Write-Host "  3. Each tab shows placeholder card 'session 3-4 in progress'" -ForegroundColor White
Write-Host "  4. /admin/rbac-v2 still works (unchanged)" -ForegroundColor White
Write-Host ""
Write-Host "Session 3 next: real UsersPage + UserAccessMap + RolesPage logic" -ForegroundColor DarkGray
