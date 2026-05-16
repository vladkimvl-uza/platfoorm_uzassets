# =====================================================================
# p133b3-grid-center.ps1  (definitive centering fix)
# =====================================================================
# Previous attempts using flex+align-items:center + width:100% + max-width
# did not center properly because in flex column-direction, width:100%
# on the child makes it occupy full cross-axis size, leaving nothing for
# align-items:center to center.
#
# This fix switches the root layout to CSS grid with 3 columns:
#   1fr | 960px | 1fr
# Pane and topbar are placed in the middle column. Side columns absorb
# all the leftover space evenly. This is unconditional centering, no
# flexbox quirks involved.
# =====================================================================

$ErrorActionPreference = "Stop"
$enc = New-Object System.Text.UTF8Encoding($false)
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$root = $PSScriptRoot
if (-not $root) { $root = (Get-Location).Path }

function Read-File($p)  { return [System.IO.File]::ReadAllText($p, $enc) }
function Write-File($p, $text) { [System.IO.File]::WriteAllText($p, $text, $enc) }
function Backup-File($p) {
    $bak = "$p.bakP133b3.$stamp"
    Copy-Item -LiteralPath $p -Destination $bak -Force
}
function Apply-Patch-EitherOf($path, $variants, $newBlock, $label) {
    Write-Host "[*] $label" -ForegroundColor Yellow
    if (-not (Test-Path -LiteralPath $path)) { throw "File not found: $path" }
    $src = Read-File $path
    $fileHasCRLF = $src.Contains("`r`n")
    $srcN = $src.Replace("`r`n", "`n")
    $newN = $newBlock.Replace("`r`n", "`n")
    if ($srcN.Contains($newN)) {
        Write-Host "    SKIP: already applied" -ForegroundColor DarkGray
        return
    }
    $chosen = $null
    foreach ($v in $variants) {
        $vN = $v.Replace("`r`n", "`n")
        if ($srcN.Contains($vN)) { $chosen = $vN; break }
    }
    if (-not $chosen) {
        throw "Anchor NOT FOUND (none of $($variants.Count) variants) in $path"
    }
    Backup-File $path
    $patchedN = $srcN.Replace($chosen, $newN)
    if ($fileHasCRLF) { $out = $patchedN.Replace("`n", "`r`n") } else { $out = $patchedN }
    Write-File $path $out
    Write-Host "    OK" -ForegroundColor Green
}

$wizPath = Join-Path $root "frontend\src\views\MfaOnboarding.vue"

# ───────────────────────────────────────────────────────────────────────
# [1/3] .mfa-ob-root — switch to CSS grid 1fr / 960px / 1fr
# ───────────────────────────────────────────────────────────────────────
# Possible existing states:
#   - p133b state (original) : flex + no centering
#   - p133b1 state           : flex + align-items center + justify-content center
#   - p133b2 state            : flex + align-items center (no justify)
$rootV1 = @'
.mfa-ob-root {
  min-height: 100vh;
  background: linear-gradient(180deg, #F1F3F8 0%, #E8ECF3 100%);
  padding: 24px 40px 40px;
  display: flex;
  flex-direction: column;
  gap: 24px;
  color: #1E2A4A;
  font-weight: 400;
}
'@
$rootV2 = @'
.mfa-ob-root {
  min-height: 100vh;
  background: linear-gradient(180deg, #F1F3F8 0%, #E8ECF3 100%);
  padding: 24px 40px 40px;
  display: flex;
  flex-direction: column;
  gap: 24px;
  align-items: center;        /* center children horizontally */
  justify-content: center;    /* center children vertically */
  color: #1E2A4A;
  font-weight: 400;
}
'@
$rootV3 = @'
.mfa-ob-root {
  min-height: 100vh;
  background: linear-gradient(180deg, #F1F3F8 0%, #E8ECF3 100%);
  padding: 24px 40px 40px;
  display: flex;
  flex-direction: column;
  gap: 24px;
  align-items: center;        /* center children horizontally */
  color: #1E2A4A;
  font-weight: 400;
}
'@
$rootNew = @'
.mfa-ob-root {
  min-height: 100vh;
  background: linear-gradient(180deg, #F1F3F8 0%, #E8ECF3 100%);
  padding: 24px 16px 40px;
  /* Pack 13.3.3: explicit 3-column grid for unconditional centering */
  display: grid;
  grid-template-columns: 1fr min(960px, 100%) 1fr;
  grid-template-rows: auto 1fr;
  row-gap: 24px;
  color: #1E2A4A;
  font-weight: 400;
}
'@
Apply-Patch-EitherOf $wizPath @($rootV2, $rootV3, $rootV1) $rootNew "[1/3] .mfa-ob-root: CSS grid 3-column layout"

# ───────────────────────────────────────────────────────────────────────
# [2/3] .mfa-ob-topbar — place in middle column
# ───────────────────────────────────────────────────────────────────────
$tbV1 = @'
.mfa-ob-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 0 4px;
}
'@
$tbV2 = @'
.mfa-ob-topbar {
  width: 100%;
  max-width: 980px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 0 4px;
}
'@
$tbNew = @'
.mfa-ob-topbar {
  grid-column: 2;       /* middle column of the 3-col grid */
  grid-row: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 0 4px;
}
'@
Apply-Patch-EitherOf $wizPath @($tbV2, $tbV1) $tbNew "[2/3] .mfa-ob-topbar: place in middle grid column"

# ───────────────────────────────────────────────────────────────────────
# [3/3] .mfa-ob-pane — place in middle column, drop flex/width nonsense
# ───────────────────────────────────────────────────────────────────────
$paneV1 = @'
.mfa-ob-pane {
  flex: 1;
  background: white;
  border-radius: 18px;
  padding: 40px;
  display: grid;
  grid-template-columns: 1fr 320px;
  gap: 48px;
  align-items: center;
  box-shadow: 0 24px 64px rgba(15,23,60,.08), 0 8px 24px rgba(15,23,60,.04);
}
'@
$paneV2 = @'
.mfa-ob-pane {
  flex: 1;
  max-width: 980px;
  width: 100%;
  margin: 0 auto;          /* center horizontally */
  align-self: center;      /* center vertically inside flex root */
  background: white;
  border-radius: 18px;
  padding: 40px;
  display: grid;
  grid-template-columns: 1fr 320px;
  gap: 48px;
  align-items: center;
  box-shadow: 0 24px 64px rgba(15,23,60,.08), 0 8px 24px rgba(15,23,60,.04);
}
'@
$paneV3 = @'
.mfa-ob-pane {
  width: 100%;
  max-width: 980px;
  background: white;
  border-radius: 18px;
  padding: 40px;
  display: grid;
  grid-template-columns: 1fr 320px;
  gap: 48px;
  align-items: center;
  box-shadow: 0 24px 64px rgba(15,23,60,.08), 0 8px 24px rgba(15,23,60,.04);
}
'@
$paneNew = @'
.mfa-ob-pane {
  grid-column: 2;       /* middle column of the 3-col grid */
  grid-row: 2;
  width: 100%;
  background: white;
  border-radius: 18px;
  padding: 40px;
  display: grid;
  grid-template-columns: 1fr 320px;
  gap: 48px;
  align-items: center;
  box-shadow: 0 24px 64px rgba(15,23,60,.08), 0 8px 24px rgba(15,23,60,.04);
}
'@
Apply-Patch-EitherOf $wizPath @($paneV3, $paneV2, $paneV1) $paneNew "[3/3] .mfa-ob-pane: place in middle grid column"

# ───────────────────────────────────────────────────────────────────────
# Rebuild + restart
# ───────────────────────────────────────────────────────────────────────
function Find-Container($pattern) {
    $all = (docker ps --format "{{.Names}}" 2>$null) -split "`n" | Where-Object { $_ -and $_.Trim() }
    foreach ($name in $all) { if ($name -match $pattern) { return $name } }
    return $null
}
$fe = Find-Container "frontend|^uza-frontend"
if (-not $fe) {
    Write-Host "[!] Frontend container not running, rebuild manually" -ForegroundColor Yellow
} else {
    Write-Host ""
    Write-Host "[=] Rebuilding production bundle" -ForegroundColor Cyan
    docker exec -e NODE_OPTIONS=--max-old-space-size=4096 -e VITE_API_BASE_URL= $fe npx vite build
    if ($LASTEXITCODE -ne 0) { throw "vite build failed" }
    Write-Host "    build OK" -ForegroundColor Green
    Write-Host "[=] Restarting frontend container" -ForegroundColor Cyan
    docker restart $fe | Out-Null
    Write-Host "    restarted" -ForegroundColor Green
}

Write-Host ""
Write-Host "===================================================================" -ForegroundColor Green
Write-Host " p133b3 COMPLETE - wizard now sits in dead-center middle column" -ForegroundColor Green
Write-Host "===================================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Hard refresh browser (Ctrl+Shift+R) - the wizard should now be" -ForegroundColor Cyan
Write-Host "in the exact center of the viewport, with equal empty space on" -ForegroundColor Cyan
Write-Host "both left and right sides." -ForegroundColor Cyan
