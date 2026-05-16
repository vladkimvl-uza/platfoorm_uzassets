# =====================================================================
# p141b-rbac-v3-add-groups.ps1  (extension to p141 — adds 5th tab "Группы")
# =====================================================================
# Run AFTER p141 has been applied successfully.
#
# Adds:
#   1. views/rbac-v3/GroupsPage.vue (skeleton)
#   2. Updates RBACShell.vue: 5 tabs instead of 4 (insert "Группы" between
#      Роли and Email-правила)
#   3. Router: add rbac-v3-groups child route
#   4. Updates usePermissions.ts: process user.groups[].permissions
#      so Access-карта can show "via group: X" as source
#
# Idempotent (safe to re-run).
# =====================================================================

$ErrorActionPreference = "Stop"
$enc = New-Object System.Text.UTF8Encoding($false)
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$root = $PSScriptRoot
if (-not $root) { $root = (Get-Location).Path }

function Read-File($p)  { return [System.IO.File]::ReadAllText($p, $enc) }
function Write-File($p, $text) { [System.IO.File]::WriteAllText($p, $text, $enc) }
function Ensure-Dir($d) {
    if (-not (Test-Path -LiteralPath $d)) { New-Item -ItemType Directory -Path $d -Force | Out-Null }
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
    $bak = "$path.bakP141b.$stamp"
    Copy-Item -LiteralPath $path -Destination $bak -Force
    Write-Host "    backup: $bak" -ForegroundColor DarkGray
    $patchedN = $srcN.Replace($oldN, $newN)
    if ($fileHasCRLF) { $out = $patchedN.Replace("`n", "`r`n") } else { $out = $patchedN }
    Write-File $path $out
    Write-Host "    OK" -ForegroundColor Green
}

$fe = "frontend\src"

# ───────────────────────────────────────────────────────────────────────
# [1/4] views/rbac-v3/GroupsPage.vue — skeleton
# ───────────────────────────────────────────────────────────────────────
$groupsPage = @'
<script setup lang="ts">
/** Session 3 will fill this with list + editor for user groups. */
</script>

<template>
  <div class="rv3-page">
    <div class="rv3-placeholder">
      <div class="rv3-ph-eyebrow">RBAC v3 · Сессия 3</div>
      <div class="rv3-ph-title">Группы</div>
      <div class="rv3-ph-text">
        Sidebar со списком групп (по отделам / по проектам),
        центральный редактор: участники chips + групповые разрешения.
        Разрешения группы выдаются всем участникам поверх их ролей.
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
Write-NewFile (Join-Path $root "$fe\views\rbac-v3\GroupsPage.vue") $groupsPage "[1/4] views/rbac-v3/GroupsPage.vue"

# ───────────────────────────────────────────────────────────────────────
# [2/4] RBACShell.vue — change 4 tabs to 5, insert "Группы"
# ───────────────────────────────────────────────────────────────────────
$oldTabs = @'
const TABS = [
  { name: 'rbac-v3-users',  label: 'Пользователи' },
  { name: 'rbac-v3-roles',  label: 'Роли' },
  { name: 'rbac-v3-email',  label: 'Email-правила' },
  { name: 'rbac-v3-audit',  label: 'Аудит' },
];
'@
$newTabs = @'
const TABS = [
  { name: 'rbac-v3-users',  label: 'Пользователи' },
  { name: 'rbac-v3-roles',  label: 'Роли' },
  { name: 'rbac-v3-groups', label: 'Группы' },
  { name: 'rbac-v3-email',  label: 'Email-правила' },
  { name: 'rbac-v3-audit',  label: 'Аудит' },
];
'@
Apply-Patch (Join-Path $root "$fe\views\rbac-v3\RBACShell.vue") $oldTabs $newTabs "[2/4] RBACShell.vue: add Группы tab"

# ───────────────────────────────────────────────────────────────────────
# [3/4] router/index.ts — add rbac-v3-groups child
# ───────────────────────────────────────────────────────────────────────
$oldRoute = '            { path: "roles", name: "rbac-v3-roles", component: () => import("@/views/rbac-v3/RolesPage.vue") },
            { path: "email-rules", name: "rbac-v3-email", component: () => import("@/views/rbac-v3/EmailRulesPage.vue") },'
$newRoute = '            { path: "roles", name: "rbac-v3-roles", component: () => import("@/views/rbac-v3/RolesPage.vue") },
            { path: "groups", name: "rbac-v3-groups", component: () => import("@/views/rbac-v3/GroupsPage.vue") },
            { path: "email-rules", name: "rbac-v3-email", component: () => import("@/views/rbac-v3/EmailRulesPage.vue") },'
Apply-Patch (Join-Path $root "$fe\router\index.ts") $oldRoute $newRoute "[3/4] router: rbac-v3-groups route"

# ───────────────────────────────────────────────────────────────────────
# [4/4] usePermissions.ts — process user.groups[].permissions
# ───────────────────────────────────────────────────────────────────────
$oldFn = '    // Extract permission codes from user.permissions (array of objects or strings)
    const perms = (user.permissions || []) as Array<string | { code: string; is_denied?: boolean }>;
    const grantedCodes: string[] = [];
    const deniedCodes: string[] = [];
    for (const p of perms) {
      if (typeof p === "string") {
        grantedCodes.push(p);
      } else if (p && typeof p === "object") {
        if (p.is_denied) deniedCodes.push(p.code);
        else grantedCodes.push(p.code);
      }
    }'
$newFn = '    // Extract permission codes from user.permissions (direct grants)
    const perms = (user.permissions || []) as Array<string | { code: string; is_denied?: boolean }>;
    const grantedCodes: string[] = [];
    const deniedCodes: string[] = [];
    const codeSource: Record<string, string> = {}; // code -> origin
    for (const p of perms) {
      if (typeof p === "string") {
        grantedCodes.push(p);
        codeSource[p] = codeSource[p] || "manual grant";
      } else if (p && typeof p === "object") {
        if (p.is_denied) deniedCodes.push(p.code);
        else {
          grantedCodes.push(p.code);
          codeSource[p.code] = codeSource[p.code] || "manual grant";
        }
      }
    }
    // Pack 141b: group-derived permissions
    // user.groups: [{ code, name, permissions: [{code, ...}] }]
    const groups = (user.groups || []) as Array<{ code?: string; name?: string; permissions?: Array<string | { code: string }> }>;
    for (const g of groups) {
      const gName = g.name || g.code || "group";
      for (const gp of (g.permissions || [])) {
        const code = typeof gp === "string" ? gp : gp?.code;
        if (!code) continue;
        if (!grantedCodes.includes(code)) grantedCodes.push(code);
        if (!codeSource[code]) codeSource[code] = `via group: ${gName}`;
      }
    }'
Apply-Patch (Join-Path $root "$fe\composables\usePermissions.ts") $oldFn $newFn "[4/4] usePermissions: process groups"

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
Write-Host " p141b COMPLETE — RBAC v3 now has 5 tabs (Users/Roles/Groups/Email/Audit)" -ForegroundColor Green
Write-Host "===================================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Hard refresh (Ctrl+Shift+R). New 'Группы' tab appears between Роли and Email-правила." -ForegroundColor Cyan
