# =====================================================================
# p133b1-onboarding-center-and-hide-code.ps1
# =====================================================================
# Two visual fixes for MfaOnboarding wizard:
#   1. Center the wizard pane horizontally + vertically. Currently on wide
#      monitors the layout sticks to the left because pane has flex:1 with
#      no max-width. Fix: max-width 980px + auto margins + root flex
#      align-items/justify-content center.
#   2. Step 3 ("Test code") fake phone showed literal code "372 941",
#      which misleads users into thinking that's the real code to type.
#      Replace with blurred placeholder "••• •••" + clearer hint
#      "Откройте чат с @UzAssets_bot — код пришёл туда".
#
# Four point-edits in frontend/src/views/MfaOnboarding.vue.
# After patch: rerun `npx vite build` + recreate frontend container,
# or use the same p134 emergency-build flow.
# =====================================================================

$ErrorActionPreference = "Stop"
$enc = New-Object System.Text.UTF8Encoding($false)
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$root = $PSScriptRoot
if (-not $root) { $root = (Get-Location).Path }
Write-Host "[i] Working root: $root" -ForegroundColor Cyan

function Read-File($p)  { return [System.IO.File]::ReadAllText($p, $enc) }
function Write-File($p, $text) { [System.IO.File]::WriteAllText($p, $text, $enc) }
function Backup-File($p) {
    $bak = "$p.bakP133b1.$stamp"
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
    $hasOld = $srcN.Contains($oldN)
    $hasNew = $srcN.Contains($newN)
    if (-not $hasOld -and $hasNew) {
        Write-Host "    SKIP: already applied" -ForegroundColor DarkGray
        return
    }
    if (-not $hasOld) { throw "Anchor NOT FOUND in $path ($label)" }
    $count = 0; $idx = 0
    while (($idx = $srcN.IndexOf($oldN, $idx)) -ge 0) { $count++; $idx += $oldN.Length }
    if ($count -gt 1) { throw "Anchor NOT UNIQUE ($count) in $label" }
    Backup-File $path
    $patchedN = $srcN.Replace($oldN, $newN)
    if ($fileHasCRLF) { $patchedOut = $patchedN.Replace("`n", "`r`n") } else { $patchedOut = $patchedN }
    Write-File $path $patchedOut
    Write-Host "    OK" -ForegroundColor Green
}

$f = Join-Path $root "frontend\src\views\MfaOnboarding.vue"

# ───────────────────────────────────────────────────────────────────────
# [1/4] .mfa-ob-pane — add max-width 980px, auto margin, self-center
# ───────────────────────────────────────────────────────────────────────
$old1 = @'
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
$new1 = @'
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
Apply-Patch $f $old1 $new1 "[1/4] .mfa-ob-pane: max-width 980px + center"

# ───────────────────────────────────────────────────────────────────────
# [2/4] .mfa-ob-root + .mfa-ob-topbar — center children, match topbar width
# ───────────────────────────────────────────────────────────────────────
$old2 = @'
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
.mfa-ob-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 0 4px;
}
'@
$new2 = @'
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
Apply-Patch $f $old2 $new2 "[2/4] .mfa-ob-root + topbar: center alignment"

# ───────────────────────────────────────────────────────────────────────
# [3/4] Step 3 phone — remove literal code "372 941", use placeholder
# ───────────────────────────────────────────────────────────────────────
$old3 = @"
                <div class="mfa-ob-phone-msg mfa-ob-phone-msg-code">
                  <div class="mfa-ob-pc-label" style="margin-bottom:5px">Тестовый код</div>
                  <div class="mfa-ob-phone-code">372 941</div>
                  <div class="mfa-ob-phone-code-hint">Введите в браузер. Истекает через 5 минут.</div>
                  <div class="mfa-ob-phone-time">9:41</div>
                </div>
"@
$new3 = @"
                <div class="mfa-ob-phone-msg mfa-ob-phone-msg-code">
                  <div class="mfa-ob-pc-label" style="margin-bottom:5px">Тестовый код</div>
                  <div class="mfa-ob-phone-code mfa-ob-phone-code-blur">••• •••</div>
                  <div class="mfa-ob-phone-code-hint">Откройте чат с @UzAssets_bot — код пришёл туда.</div>
                  <div class="mfa-ob-phone-time">9:41</div>
                </div>
"@
Apply-Patch $f $old3 $new3 "[3/4] step-3 phone: literal code -> placeholder"

# ───────────────────────────────────────────────────────────────────────
# [4/4] CSS for .mfa-ob-phone-code-blur (placeholder style)
# ───────────────────────────────────────────────────────────────────────
$old4 = @'
.mfa-ob-phone-code {
  font-family: ui-monospace, "SF Mono", Menlo, monospace;
  font-size: 24px; font-weight: 500;
  color: white; letter-spacing: 0.12em;
  text-align: center; padding: 6px 0;
  animation: mfa-code-reveal .6s ease;
}
'@
$new4 = @'
.mfa-ob-phone-code {
  font-family: ui-monospace, "SF Mono", Menlo, monospace;
  font-size: 24px; font-weight: 500;
  color: white; letter-spacing: 0.12em;
  text-align: center; padding: 6px 0;
  animation: mfa-code-reveal .6s ease;
}
.mfa-ob-phone-code-blur {
  color: rgba(255,255,255,.55);
  letter-spacing: 0.16em;
  animation: none;
}
'@
Apply-Patch $f $old4 $new4 "[4/4] CSS: .mfa-ob-phone-code-blur"

# ───────────────────────────────────────────────────────────────────────
# Rebuild prod bundle so changes are visible (current frontend = vite preview)
# ───────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "[=] Rebuilding production bundle" -ForegroundColor Cyan

function Find-Container($pattern) {
    try {
        $all = (docker ps --format "{{.Names}}" 2>$null) -split "`n" | Where-Object { $_ -and $_.Trim() }
        foreach ($name in $all) { if ($name -match $pattern) { return $name } }
    } catch {}
    return $null
}
$fe = Find-Container "frontend|^uza-frontend"
if (-not $fe) {
    Write-Host "    Frontend container not running. Rebuild manually:" -ForegroundColor Yellow
    Write-Host "      docker exec <frontend> npx vite build" -ForegroundColor White
} else {
    Write-Host "    container: $fe" -ForegroundColor DarkGray
    docker exec -e NODE_OPTIONS=--max-old-space-size=4096 $fe npx vite build
    if ($LASTEXITCODE -ne 0) {
        Write-Host "    vite build failed" -ForegroundColor Red
        throw "build failed"
    }
    Write-Host "    Build OK" -ForegroundColor Green

    # vite preview serves from dist/ — it does not auto-watch dist/.
    # After a rebuild, the new files are on disk but the running preview
    # already mapped index.html into memory. A container restart picks up
    # the rebuilt assets cleanly.
    Write-Host ""
    Write-Host "[=] Restarting frontend container to pick up rebuilt dist/" -ForegroundColor Cyan
    docker restart $fe | Out-Null
    Write-Host "    restarted" -ForegroundColor Green
}

Write-Host ""
Write-Host "===================================================================" -ForegroundColor Green
Write-Host " p133b1 COMPLETE" -ForegroundColor Green
Write-Host "===================================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Verify in browser (Ctrl+Shift+R):" -ForegroundColor Cyan
Write-Host "  - wizard should now sit centered on the screen" -ForegroundColor White
Write-Host "  - step 3: fake phone shows greyed out dots, not a literal code" -ForegroundColor White
