# =====================================================================
# p133b5-fullwidth-root.ps1   (root cause fix)
# =====================================================================
# Diagnosis: #app in main.css has `display: flex; width: 100vw`. That
# makes .mfa-ob-root a flex item which, by default flex-grow:0, only
# takes content size — it never spans the viewport, so the inner grid
# 1fr|960|1fr collapses against an already-narrow container, leaving
# pane left-aligned.
#
# Fix: in the existing global override <style> block, force
#   .mfa-ob-root { width: 100vw !important; flex: 1 1 100vw !important; }
# so it always claims the full viewport width regardless of #app's
# flex layout. Inner grid then has the full width to distribute.
# =====================================================================

$ErrorActionPreference = "Stop"
$enc = New-Object System.Text.UTF8Encoding($false)
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$root = $PSScriptRoot
if (-not $root) { $root = (Get-Location).Path }

function Read-File($p)  { return [System.IO.File]::ReadAllText($p, $enc) }
function Write-File($p, $text) { [System.IO.File]::WriteAllText($p, $text, $enc) }
function Backup-File($p) {
    $bak = "$p.bakP133b5.$stamp"
    Copy-Item -LiteralPath $p -Destination $bak -Force
    Write-Host "    backup: $bak" -ForegroundColor DarkGray
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
    Backup-File $path
    $patchedN = $srcN.Replace($oldN, $newN)
    if ($fileHasCRLF) { $out = $patchedN.Replace("`n", "`r`n") } else { $out = $patchedN }
    Write-File $path $out
    Write-Host "    OK" -ForegroundColor Green
}

$wiz = Join-Path $root "frontend\src\views\MfaOnboarding.vue"

# Augment the existing global override block from p133b4 — add flex/width
# overrides to make .mfa-ob-root claim full viewport regardless of #app
$old = @'
.mfa-ob-root {
  min-height: 100vh !important;
  background: linear-gradient(180deg, #F1F3F8 0%, #E8ECF3 100%) !important;
  padding: 24px 16px 40px !important;
  display: grid !important;
  grid-template-columns: 1fr min(960px, 100%) 1fr !important;
  grid-template-rows: auto 1fr !important;
  row-gap: 24px !important;
  column-gap: 0 !important;
  color: #1E2A4A !important;
  font-weight: 400 !important;
  margin: 0 !important;
  box-sizing: border-box !important;
}
'@
$new = @'
.mfa-ob-root {
  /* #app is a flex container (main.css) — without these the root
     collapses to content width and prevents proper grid centering. */
  width: 100vw !important;
  min-width: 100vw !important;
  flex: 1 1 100vw !important;
  min-height: 100vh !important;
  background: linear-gradient(180deg, #F1F3F8 0%, #E8ECF3 100%) !important;
  padding: 24px 16px 40px !important;
  display: grid !important;
  grid-template-columns: 1fr min(960px, 100%) 1fr !important;
  grid-template-rows: auto 1fr !important;
  row-gap: 24px !important;
  column-gap: 0 !important;
  color: #1E2A4A !important;
  font-weight: 400 !important;
  margin: 0 !important;
  box-sizing: border-box !important;
}
'@
Apply-Patch $wiz $old $new "[1/1] .mfa-ob-root: width:100vw + flex:1 (escape #app's flex item sizing)"

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
    Write-Host "[=] Restarting frontend container" -ForegroundColor Cyan
    docker restart $fe | Out-Null
    Write-Host "    restarted" -ForegroundColor Green
}

Write-Host ""
Write-Host "===================================================================" -ForegroundColor Green
Write-Host " p133b5 COMPLETE — wizard should now span full viewport, pane centered" -ForegroundColor Green
Write-Host "===================================================================" -ForegroundColor Green
