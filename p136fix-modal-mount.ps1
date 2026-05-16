# =====================================================================
# p136-fix-modal-mount.ps1   (patch the missing [7b] from p136)
# =====================================================================
# Recovers the failed [7b/9] step from p136-invest-credit-unify.ps1.
# All other patches (1-7, 8, 9) already applied successfully.
# Anchor was incorrect — actual section header is the long MODALS divider.
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
    $bak = "$path.bakP136fix.$stamp"
    Copy-Item -LiteralPath $path -Destination $bak -Force
    Write-Host "    backup: $bak" -ForegroundColor DarkGray
    $patchedN = $srcN.Replace($oldN, $newN)
    if ($fileHasCRLF) { $out = $patchedN.Replace("`n", "`r`n") } else { $out = $patchedN }
    Write-File $path $out
    Write-Host "    OK" -ForegroundColor Green
}

$ip = Join-Path $root "frontend\src\views\InvestProjects.vue"

# Mount the CAPEX modal right at the start of the MODALS section
$old = @'
    <!-- ─── MODALS ─────────────────────────────────────── -->
    <ProjectDrillModal
'@
$new = @'
    <!-- ─── MODALS ─────────────────────────────────────── -->
    <CapexQuarterlyModal v-if="capexModalOpen" :data="data" @close="capexModalOpen = false" />
    <ProjectDrillModal
'@
Apply-Patch $ip $old $new "[7b-fix] InvestProjects: mount CapexQuarterlyModal"

# Rebuild + restart
function Find-Container($pattern) {
    $all = (docker ps --format "{{.Names}}" 2>$null) -split "`n" | Where-Object { $_ -and $_.Trim() }
    foreach ($name in $all) { if ($name -match $pattern) { return $name } }
    return $null
}
$fe = Find-Container "frontend|^uza-frontend"
if (-not $fe) {
    Write-Host "[!] Frontend container not running" -ForegroundColor Yellow
} else {
    Write-Host ""
    Write-Host "[=] Clearing Vite cache + rebuilding" -ForegroundColor Cyan
    docker exec $fe sh -c "rm -rf /app/dist /app/node_modules/.vite 2>/dev/null; true"
    docker exec -e NODE_OPTIONS=--max-old-space-size=4096 -e VITE_API_BASE_URL= $fe npx vite build
    if ($LASTEXITCODE -ne 0) { throw "vite build failed" }
    Write-Host "    build OK" -ForegroundColor Green
    docker restart $fe | Out-Null
    Write-Host "    frontend restarted" -ForegroundColor Green
}

Write-Host ""
Write-Host "===================================================================" -ForegroundColor Green
Write-Host " p136 complete (with fix)" -ForegroundColor Green
Write-Host "===================================================================" -ForegroundColor Green
