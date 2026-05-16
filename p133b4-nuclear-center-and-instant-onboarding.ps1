# =====================================================================
# p133b4-nuclear-center-and-instant-onboarding.ps1
# =====================================================================
# Two definitive fixes:
#
# 1. CENTERING — uses GLOBAL non-scoped CSS with !important inside the
#    MfaOnboarding.vue file. This beats ALL scoped CSS regardless of
#    whether previous patches actually got applied or not. Method:
#    insert a new <style> block (no `scoped` attribute) above the
#    existing <style scoped> block. CSS hits the same .mfa-ob-* selectors
#    but at higher specificity due to !important.
#
# 2. ONBOARDING APPEARS INSTANTLY — currently after login the user briefly
#    sees the dashboard before the async router guard fetches
#    /mfa/onboarding/status and bounces them to the wizard. Fix: check
#    onboarding status RIGHT AFTER login (in LoginV2 and LoginMfaStep),
#    BEFORE pushing the user anywhere. No flash, instant wizard.
#
# Files touched (idempotent):
#   frontend/src/views/MfaOnboarding.vue   [inject global style block]
#   frontend/src/views/LoginV2.vue          [pre-redirect onboarding check]
#   frontend/src/views/LoginMfaStep.vue     [pre-redirect onboarding check]
# =====================================================================

$ErrorActionPreference = "Stop"
$enc = New-Object System.Text.UTF8Encoding($false)
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$root = $PSScriptRoot
if (-not $root) { $root = (Get-Location).Path }

function Read-File($p)  { return [System.IO.File]::ReadAllText($p, $enc) }
function Write-File($p, $text) { [System.IO.File]::WriteAllText($p, $text, $enc) }
function Backup-File($p) {
    $bak = "$p.bakP133b4.$stamp"
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

# ───────────────────────────────────────────────────────────────────────
# [1/3] MfaOnboarding.vue — inject global !important CSS above scoped block
# ───────────────────────────────────────────────────────────────────────
# Marker comment is the idempotency anchor.
$wiz = Join-Path $root "frontend\src\views\MfaOnboarding.vue"
$old1 = @'
<style scoped>
'@
$new1 = @'
<!-- Pack 13.3.4: global override styles — beat any conflicting scoped CSS -->
<style>
/* === Centering override (!important kills all earlier flex/grid attempts) === */
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
.mfa-ob-topbar {
  grid-column: 2 !important;
  grid-row: 1 !important;
  width: 100% !important;
  max-width: none !important;
  margin: 0 !important;
  align-self: start !important;
  justify-self: stretch !important;
}
.mfa-ob-pane {
  grid-column: 2 !important;
  grid-row: 2 !important;
  width: 100% !important;
  max-width: none !important;
  flex: initial !important;
  margin: 0 !important;
  align-self: start !important;
  justify-self: stretch !important;
}
</style>

<style scoped>
'@
Apply-Patch $wiz $old1 $new1 "[1/3] MfaOnboarding.vue: inject global !important centering CSS"

# ───────────────────────────────────────────────────────────────────────
# [2/3] LoginV2.vue — check onboarding before pushing to dashboard
# ───────────────────────────────────────────────────────────────────────
$loginv2 = Join-Path $root "frontend\src\views\LoginV2.vue"
$old2 = @'
    auth.setTokens({
      access_token: resp.access_token,
      refresh_token: resp.refresh_token,
      token_type: resp.token_type ?? "Bearer",
      expires_in: resp.expires_in ?? 1800,
    });
    const me = await authApi.me();
    auth.setUser(me);
    const target = (route.query.redirect as string | undefined) ?? "/";
    void router.push(target);
'@
$new2 = @'
    auth.setTokens({
      access_token: resp.access_token,
      refresh_token: resp.refresh_token,
      token_type: resp.token_type ?? "Bearer",
      expires_in: resp.expires_in ?? 1800,
    });
    const me = await authApi.me();
    auth.setUser(me);
    // Pack 13.3.4: check onboarding BEFORE redirect — no flash of dashboard
    try {
      const ob = await mfaApi.onboardingStatus();
      if (ob.needed) {
        void router.replace({ name: "mfa-onboarding" });
        return;
      }
    } catch { /* non-fatal: fall through to default redirect */ }
    const target = (route.query.redirect as string | undefined) ?? "/";
    void router.push(target);
'@
Apply-Patch $loginv2 $old2 $new2 "[2/3] LoginV2.vue: pre-redirect onboarding check"

# ───────────────────────────────────────────────────────────────────────
# [3/3] LoginMfaStep.vue — check onboarding before pushing to dashboard
# ───────────────────────────────────────────────────────────────────────
$loginmfa = Join-Path $root "frontend\src\views\LoginMfaStep.vue"
$old3 = @'
    const tokens = await mfaApi.verifyMfa(payload);
    auth.setTokens(tokens);
    const me = await authApi.me();
    auth.setUser(me);
    sessionStorage.removeItem("uza_mfa_challenge");
    const target = (route.query.redirect as string | undefined) ?? "/";
    void router.push(target);
'@
$new3 = @'
    const tokens = await mfaApi.verifyMfa(payload);
    auth.setTokens(tokens);
    const me = await authApi.me();
    auth.setUser(me);
    sessionStorage.removeItem("uza_mfa_challenge");
    // Pack 13.3.4: check onboarding BEFORE redirect — no flash of dashboard
    try {
      const ob = await mfaApi.onboardingStatus();
      if (ob.needed) {
        void router.replace({ name: "mfa-onboarding" });
        return;
      }
    } catch { /* non-fatal: fall through to default redirect */ }
    const target = (route.query.redirect as string | undefined) ?? "/";
    void router.push(target);
'@
Apply-Patch $loginmfa $old3 $new3 "[3/3] LoginMfaStep.vue: pre-redirect onboarding check"

# ───────────────────────────────────────────────────────────────────────
# Rebuild + restart frontend (with cache invalidation)
# ───────────────────────────────────────────────────────────────────────
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
    Write-Host "[=] Clearing Vite cache, rebuilding production bundle" -ForegroundColor Cyan
    # Force-remove old dist + Vite cache so we don't accidentally serve stale chunks
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
Write-Host " p133b4 COMPLETE" -ForegroundColor Green
Write-Host "===================================================================" -ForegroundColor Green
Write-Host ""
Write-Host "REQUIRED in browser:" -ForegroundColor Yellow
Write-Host "  1. Open DevTools (F12) -> Network tab -> check 'Disable cache'" -ForegroundColor White
Write-Host "  2. Ctrl+Shift+R (hard refresh)" -ForegroundColor White
Write-Host "  3. Logout, log back in as the test user (no MFA configured)" -ForegroundColor White
Write-Host ""
Write-Host "Expected:" -ForegroundColor Cyan
Write-Host "  - Onboarding wizard appears INSTANTLY after login (no flash of dashboard)" -ForegroundColor White
Write-Host "  - Wizard sits in dead center of the screen with equal margins" -ForegroundColor White
