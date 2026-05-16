# =====================================================================
# p144-rbac-v3-cleanup-and-impersonate.ps1   (RBAC v3 FINAL pack)
# =====================================================================
# Two purposes:
#
# A. preview_token handler + impersonate banner (completes p143d)
#    1. AppShell.vue picks up ?preview_token= from URL
#    2. Swaps it into localStorage (saving original token to _backup)
#    3. Shows fixed purple top-banner: "Вы вошли как X · Вернуться"
#    4. "Вернуться" button restores original token + reloads
#
# B. Cleanup legacy /admin/rbac-v2 + RBACMatrix.vue (1688 LOC) +
#    redirects + sidebar entry + bak files older than 7 days.
#
# IMPORTANT: This permanently removes the old RBAC UI. The /admin/rbac-v2
# URL will redirect to /admin/rbac-v3 to preserve bookmarks. The
# /admin/companies redirect target is updated to /admin/companies-legacy
# (which still works).
#
# To roll back: restore from backup files .bakP144.<stamp>
# =====================================================================

$ErrorActionPreference = "Stop"
$enc = New-Object System.Text.UTF8Encoding($false)
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$root = $PSScriptRoot
if (-not $root) { $root = (Get-Location).Path }

function Read-File($p)  { return [System.IO.File]::ReadAllText($p, $enc) }
function Write-File($p, $text) { [System.IO.File]::WriteAllText($p, $text, $enc) }
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
    Copy-Item -LiteralPath $path -Destination "$path.bakP144.$stamp" -Force
    Write-Host "    backup: $path.bakP144.$stamp" -ForegroundColor DarkGray
    $patched = $srcN.Replace($oldN, $newN)
    if ($hasCRLF) { $out = $patched.Replace("`n", "`r`n") } else { $out = $patched }
    Write-File $path $out
    Write-Host "    OK" -ForegroundColor Green
}
function Remove-File-Safe($path, $label) {
    Write-Host "[*] $label" -ForegroundColor Yellow
    if (-not (Test-Path -LiteralPath $path)) {
        Write-Host "    SKIP: already absent" -ForegroundColor DarkGray
        return
    }
    Copy-Item -LiteralPath $path -Destination "$path.bakP144-removed.$stamp" -Force
    Remove-Item -LiteralPath $path -Force
    Write-Host "    REMOVED (backup: .bakP144-removed.$stamp)" -ForegroundColor Green
}

$fe = "frontend\src"

# ═══════════════════════════════════════════════════════════════════════
# PART A: preview_token handler + impersonate banner
# ═══════════════════════════════════════════════════════════════════════

# A1. Add an ImpersonateBanner.vue component
$banner = @'
<script setup lang="ts">
defineProps<{ targetEmail: string }>();
defineEmits<{ (e: 'exit'): void }>();
</script>

<template>
  <div class="rv3-imp-banner">
    <div class="rv3-imp-l">
      <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="8" cy="5" r="2.5"/><path d="M3 13c0-2.5 2-4 5-4s5 1.5 5 4"/></svg>
      <span>Вы вошли как <strong>{{ targetEmail }}</strong> (режим просмотра, 30 мин)</span>
    </div>
    <button class="rv3-imp-exit" @click="$emit('exit')">
      Вернуться в свой аккаунт
    </button>
  </div>
</template>

<style scoped>
.rv3-imp-banner {
  position: fixed; top: 0; left: 0; right: 0;
  height: 36px; z-index: 9999;
  background: linear-gradient(90deg, #534AB7 0%, #7F77DD 100%);
  color: #fff;
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 22px;
  font-size: 12px; font-weight: 500;
  box-shadow: 0 2px 8px rgba(83,74,183,.3);
}
.rv3-imp-l { display: flex; align-items: center; gap: 9px; }
.rv3-imp-l strong { font-weight: 600; }
.rv3-imp-exit {
  padding: 5px 12px;
  background: rgba(255,255,255,.15);
  border: 1px solid rgba(255,255,255,.25);
  color: #fff;
  border-radius: 7px;
  font-size: 11.5px; font-weight: 500;
  cursor: pointer; font-family: inherit;
  transition: background .12s;
}
.rv3-imp-exit:hover { background: rgba(255,255,255,.25); }
</style>
'@
$bannerPath = Join-Path $root "$fe\components\rbac-v3\ImpersonateBanner.vue"
if (Test-Path -LiteralPath $bannerPath) {
    Write-Host "[*] [A1] ImpersonateBanner.vue already exists, skipping" -ForegroundColor DarkGray
} else {
    Write-Host "[*] [A1] ImpersonateBanner.vue (new)" -ForegroundColor Yellow
    Write-File $bannerPath $banner
    Write-Host "    OK" -ForegroundColor Green
}

# A2. AppShell.vue — handle ?preview_token= on mount, show banner, push to body
# Find a good anchor — script setup area
$oldShellHead = '/*  AppShell.vue'
$shellPath = Join-Path $root "$fe\views\AppShell.vue"
if (-not (Test-Path -LiteralPath $shellPath)) { throw "AppShell.vue not found" }
$shellSrc = Read-File $shellPath
if ($shellSrc.Contains('ImpersonateBanner')) {
    Write-Host "[*] [A2] AppShell.vue: impersonate already wired, skipping" -ForegroundColor DarkGray
} else {
    Copy-Item -LiteralPath $shellPath -Destination "$shellPath.bakP144.$stamp" -Force
    Write-Host "[*] [A2] AppShell.vue: wire ImpersonateBanner" -ForegroundColor Yellow

    # Insert state + onMounted handler at end of <script setup>
    # We find closing </script> in script-setup block and inject above it.
    # Strategy: find the FIRST </script> (matches script setup) - safer with marker.
    $injectMark = "</script>`r`n`r`n<template>"
    $injectMarkN = "</script>`n`n<template>"
    $hasMark = $shellSrc.Contains($injectMark) -or $shellSrc.Contains($injectMarkN)
    if (-not $hasMark) {
        # Try simpler match
        $injectMark = "</script>`r`n<template>"
        $injectMarkN = "</script>`n<template>"
        $hasMark = $shellSrc.Contains($injectMark) -or $shellSrc.Contains($injectMarkN)
    }
    if (-not $hasMark) { throw "Cannot find script-template boundary in AppShell.vue" }

    $injectCode = @'

// Pack 144: preview_token handler + impersonate banner
import { ref as _impRef, onMounted as _impOnMounted } from 'vue';
import ImpersonateBanner from '@/components/rbac-v3/ImpersonateBanner.vue';
const _impEmail = _impRef<string | null>(null);
const _impActive = _impRef<boolean>(false);
_impOnMounted(() => {
  // First: detect ?preview_token in URL and stash it
  const url = new URL(window.location.href);
  const tok = url.searchParams.get('preview_token');
  const targetEmail = url.searchParams.get('preview_email');
  if (tok) {
    // Save current real token for later restore
    const currentToken = localStorage.getItem('uza_access_token');
    const currentRefresh = localStorage.getItem('uza_refresh_token');
    if (currentToken && !localStorage.getItem('uza_preview_real_token')) {
      localStorage.setItem('uza_preview_real_token', currentToken);
      if (currentRefresh) localStorage.setItem('uza_preview_real_refresh', currentRefresh);
    }
    // Apply preview token
    localStorage.setItem('uza_access_token', tok);
    localStorage.removeItem('uza_refresh_token'); // preview cannot refresh
    if (targetEmail) localStorage.setItem('uza_preview_email', targetEmail);
    // Clean URL and reload to make stores pick up new identity
    url.searchParams.delete('preview_token');
    url.searchParams.delete('preview_email');
    window.history.replaceState({}, '', url.toString());
    window.location.reload();
    return;
  }
  // Restore previous state on subsequent mounts
  if (localStorage.getItem('uza_preview_real_token')) {
    _impActive.value = true;
    _impEmail.value = localStorage.getItem('uza_preview_email') || 'другой пользователь';
  }
});
function exitImpersonate() {
  const realToken = localStorage.getItem('uza_preview_real_token');
  const realRefresh = localStorage.getItem('uza_preview_real_refresh');
  if (realToken) {
    localStorage.setItem('uza_access_token', realToken);
    if (realRefresh) localStorage.setItem('uza_refresh_token', realRefresh);
    localStorage.removeItem('uza_preview_real_token');
    localStorage.removeItem('uza_preview_real_refresh');
    localStorage.removeItem('uza_preview_email');
    window.location.href = '/';
  } else {
    // No backup — just clear preview token (forces re-login)
    localStorage.removeItem('uza_access_token');
    localStorage.removeItem('uza_preview_email');
    window.location.href = '/login';
  }
}

'@

    # Inject before </script>
    if ($shellSrc.Contains("</script>`r`n<template>")) {
        $newShellSrc = $shellSrc.Replace("</script>`r`n<template>", $injectCode + "</script>`r`n<template>")
    } elseif ($shellSrc.Contains("</script>`n<template>")) {
        $newShellSrc = $shellSrc.Replace("</script>`n<template>", $injectCode + "</script>`n<template>")
    } elseif ($shellSrc.Contains("</script>`r`n`r`n<template>")) {
        $newShellSrc = $shellSrc.Replace("</script>`r`n`r`n<template>", $injectCode + "</script>`r`n`r`n<template>")
    } else {
        $newShellSrc = $shellSrc.Replace("</script>`n`n<template>", $injectCode + "</script>`n`n<template>")
    }

    # Add banner mount at top of template — after <template> opening tag
    # Find: <template>\n  <div ...> — inject after <template>
    $tplMarkers = @("<template>`r`n  <div", "<template>`n  <div", "<template>`r`n<div", "<template>`n<div")
    $found = $false
    foreach ($mk in $tplMarkers) {
        if ($newShellSrc.Contains($mk)) {
            $newShellSrc = $newShellSrc.Replace($mk, "<template>`r`n  <ImpersonateBanner v-if=`"_impActive`" :target-email=`"_impEmail || ''`" @exit=`"exitImpersonate`" />`r`n  <div")
            $found = $true
            break
        }
    }
    if (-not $found) {
        Write-Host "    WARNING: could not locate template root, banner not injected" -ForegroundColor Yellow
    }

    Write-File $shellPath $newShellSrc
    Write-Host "    OK" -ForegroundColor Green
}

# ═══════════════════════════════════════════════════════════════════════
# PART B: cleanup legacy /admin/rbac-v2 + RBACMatrix.vue
# ═══════════════════════════════════════════════════════════════════════

# B1. Router: remove admin-rbac-v2 route definition + update redirects to point to v3
$oldRoute = @'
        // Pack 9.1: RBAC v2 — granular access, groups, templates, change log
        {
          path: "admin/rbac-v2",
          name: "admin-rbac-v2",
          component: () => import("@/views/RBACMatrix.vue"),
          meta: { title: "RBAC v2", requiresPermission: "admin.users" },
        },
'@
$newRoute = @'
        // Pack 144: RBAC v2 removed — redirect old bookmarks to v3
        {
          path: "admin/rbac-v2",
          name: "admin-rbac-v2",
          redirect: "/admin/rbac-v3",
        },
'@
Apply-Patch (Join-Path $root "$fe\router\index.ts") $oldRoute $newRoute "[B1] router: replace RBAC v2 mount with redirect"

# Update old companies-admin redirect to point to v3 users tab
Apply-Patch (Join-Path $root "$fe\router\index.ts") `
    'redirect: "/admin/rbac-v2?tab=companies",' `
    'redirect: "/admin/companies-legacy",' `
    "[B2] router: update companies-admin redirect"

# Update audit redirect
Apply-Patch (Join-Path $root "$fe\router\index.ts") `
    'redirect: "/admin/rbac-v2?tab=audit",' `
    'redirect: "/admin/rbac-v3/audit",' `
    "[B3] router: update audit redirect to v3"

# Update security redirect
Apply-Patch (Join-Path $root "$fe\router\index.ts") `
    'redirect: "/admin/rbac-v2?tab=security",' `
    'redirect: "/admin/rbac-v3",' `
    "[B4] router: update security redirect to v3"

# Update old /rbac redirect (line ~269) to v3
Apply-Patch (Join-Path $root "$fe\router\index.ts") `
    @'
        // Pack 9.2: RBAC v1 removed — redirect to v2 matrix
        {
          path: "rbac",
          name: "rbac",
          redirect: "/admin/rbac-v2",
        },
'@ `
    @'
        // Pack 144: RBAC v1/v2 removed — redirect to v3
        {
          path: "rbac",
          name: "rbac",
          redirect: "/admin/rbac-v3",
        },
'@ `
    "[B5] router: legacy /rbac redirect now points to v3"

# B6. AppShell.vue sidebar — remove v2 entry, leave only v3
$oldSb = @'
          <!-- Pack 9.2: RBAC v2 — единая admin панель (users + groups + companies + sectors + templates) -->
          <RouterLink to="/admin/rbac-v2" class="sb-item sb-item-admin" active-class="active">
'@
# This is the OPENING. Need to find the FULL block including children + closing.
$shellSrc2 = Read-File (Join-Path $root "$fe\views\AppShell.vue")
if ($shellSrc2.Contains('/admin/rbac-v2')) {
    Write-Host "[*] [B6] AppShell.vue: remove RBAC v2 sidebar entry" -ForegroundColor Yellow
    # Find the entire <RouterLink to="/admin/rbac-v2" ...>...</RouterLink> block
    $marker = '<RouterLink to="/admin/rbac-v2"'
    $idx = $shellSrc2.IndexOf($marker)
    if ($idx -lt 0) { throw "Could not locate v2 sidebar marker" }
    # Walk back to start of preceding <!-- comment line
    $start = $shellSrc2.LastIndexOf("<!-- Pack 9.2:", $idx)
    if ($start -lt 0) { $start = $idx }
    # Find end: </RouterLink> after our marker
    $linkEnd = $shellSrc2.IndexOf('</RouterLink>', $idx)
    if ($linkEnd -lt 0) { throw "Could not find closing </RouterLink> for v2" }
    $endOfBlock = $linkEnd + '</RouterLink>'.Length
    # Include trailing newlines to keep formatting clean
    while ($endOfBlock -lt $shellSrc2.Length -and ($shellSrc2[$endOfBlock] -eq "`r" -or $shellSrc2[$endOfBlock] -eq "`n")) {
        $endOfBlock++
    }
    Copy-Item (Join-Path $root "$fe\views\AppShell.vue") "$root\$fe\views\AppShell.vue.bakP144b6.$stamp" -Force
    $newShellSrc2 = $shellSrc2.Substring(0, $start) + $shellSrc2.Substring($endOfBlock)
    # Also flip the NEW badge on v3 entry to not be needed any more (optional)
    # Actually leave it — it's still NEW until users acclimatize
    Write-File (Join-Path $root "$fe\views\AppShell.vue") $newShellSrc2
    Write-Host "    removed sidebar entry (backup: .bakP144b6.$stamp)" -ForegroundColor Green
} else {
    Write-Host "[*] [B6] AppShell.vue: v2 sidebar entry already absent" -ForegroundColor DarkGray
}

# B7. Remove legacy files
Remove-File-Safe (Join-Path $root "$fe\views\RBACMatrix.vue") "[B7] remove RBACMatrix.vue (1688 LOC)"
Remove-File-Safe (Join-Path $root "$fe\api\rbac.ts") "[B8] remove api/rbac.ts"
Remove-File-Safe (Join-Path $root "$fe\api\rbacV2.ts") "[B9] remove api/rbacV2.ts"

# B10. Verify no other file imports the removed modules
Write-Host ""
Write-Host "[=] Checking for dangling imports..." -ForegroundColor Cyan
$grepResults = @()
Get-ChildItem -Path (Join-Path $root "$fe") -Include "*.vue", "*.ts" -Recurse |
    Where-Object { $_.FullName -notmatch '\.bak' } |
    ForEach-Object {
        $content = [System.IO.File]::ReadAllText($_.FullName, $enc)
        if ($content -match 'from\s+[''"]@/api/rbac[''"]|from\s+[''"]@/api/rbacV2[''"]|@/views/RBACMatrix') {
            $grepResults += $_.FullName.Replace($root, '.')
        }
    }
if ($grepResults.Count -gt 0) {
    Write-Host "[!] WARNING: dangling imports found in:" -ForegroundColor Yellow
    foreach ($f in $grepResults) { Write-Host "    $f" -ForegroundColor Yellow }
    Write-Host "    Remove these manually or update to /api/rbacV3" -ForegroundColor Yellow
} else {
    Write-Host "    none — all good" -ForegroundColor Green
}

# B11. Clean .bak files older than 7 days
Write-Host ""
Write-Host "[=] Cleaning .bak* files older than 7 days..." -ForegroundColor Cyan
$cutoff = (Get-Date).AddDays(-7)
$oldBaks = Get-ChildItem -Path (Join-Path $root $fe) -Recurse -File |
    Where-Object { $_.Name -match '\.bak' -and $_.LastWriteTime -lt $cutoff }
$count = $oldBaks.Count
foreach ($b in $oldBaks) {
    try {
        Remove-Item -LiteralPath $b.FullName -Force
    } catch {
        Write-Host "    skip (locked): $($b.Name)" -ForegroundColor DarkGray
    }
}
Write-Host "    cleaned $count old backup files (kept newer ones)" -ForegroundColor Green

# ═══════════════════════════════════════════════════════════════════════
# Rebuild + restart
# ═══════════════════════════════════════════════════════════════════════
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
    Write-Host "[=] Rebuilding frontend (final)" -ForegroundColor Cyan
    docker exec $fec sh -c "rm -rf /app/dist /app/node_modules/.vite 2>/dev/null; true"
    docker exec -e NODE_OPTIONS=--max-old-space-size=4096 -e VITE_API_BASE_URL= $fec npx vite build 2>&1 | ForEach-Object { Write-Host $_ }
    docker restart $fec | Out-Null
    Write-Host "    restarted" -ForegroundColor Green
}

Write-Host ""
Write-Host "===================================================================" -ForegroundColor Green
Write-Host " p144 COMPLETE - RBAC v3 ROLLOUT FINISHED" -ForegroundColor Green
Write-Host "===================================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Sessions 1-4 done. Final state:" -ForegroundColor Cyan
Write-Host "  - /admin/rbac-v3 (5 tabs: Пользователи / Роли / Группы / Email / Аудит)" -ForegroundColor White
Write-Host "  - /admin/rbac-v2 -> redirects to v3 (preserves bookmarks)" -ForegroundColor White
Write-Host "  - RBACMatrix.vue (1688 LOC) deleted -> backup .bakP144-removed" -ForegroundColor White
Write-Host "  - api/rbac.ts + api/rbacV2.ts deleted -> backups" -ForegroundColor White
Write-Host "  - Impersonate banner active when preview_token detected" -ForegroundColor White
Write-Host "  - .bak files older than 7 days cleaned" -ForegroundColor White
Write-Host ""
Write-Host "TEST CHECKLIST after Ctrl+Shift+R:" -ForegroundColor Cyan
Write-Host "  1. Sidebar shows ONLY 'RBAC v3 . доступы' (v2 entry gone)" -ForegroundColor White
Write-Host "  2. /admin/rbac-v2 in browser -> redirects to /admin/rbac-v3" -ForegroundColor White
Write-Host "  3. In Пользователи -> drawer -> 'Войти как' on any non-admin user:" -ForegroundColor White
Write-Host "     - confirms with 30-min warning" -ForegroundColor White
Write-Host "     - new tab opens" -ForegroundColor White
Write-Host "     - purple banner appears top: 'Вы вошли как X . 30 мин'" -ForegroundColor White
Write-Host "     - sidebar reflects target user's permissions (modules hidden if no access)" -ForegroundColor White
Write-Host "     - 'Вернуться' restores your original account" -ForegroundColor White
