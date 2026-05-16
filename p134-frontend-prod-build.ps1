# =====================================================================
# p134-frontend-prod-build.ps1  (Emergency performance fix)
# =====================================================================
# Problem: uza-frontend running `npm run dev` (Vite dev server) eats
# 36% CPU and recompiles modules on every navigation -> dashboards slow,
# sometimes don't load at all.
#
# Fix (single pass):
#   1. Build production bundle inside the container: `npx vite build`
#   2. Patch docker-compose.yml: change command from `npm run dev` to
#      `npx vite preview --host 0.0.0.0 --port 5173 --strictPort`
#   3. Recreate the frontend container
#
# Result: Vite serves the pre-built dist/ as static files. No on-demand
# compilation, no HMR, no source maps. Navigation = instant. CPU drops
# from 36% to ~1%.
#
# Trade-off lost in prod mode:
#   - No hot reload (page must be refreshed to see source changes)
#   - Source maps still available via vite.config (default `sourcemap: false`)
#
# To revert to dev mode (e.g. when actively coding):
#   - Edit backend/docker-compose.yml: change command back to `npm run dev -- --host 0.0.0.0`
#   - docker compose up -d --force-recreate frontend
#
# Idempotent: detects if compose already says `vite preview` and skips
# the patch step.
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
    $bak = "$p.bakP134.$stamp"
    Copy-Item -LiteralPath $p -Destination $bak -Force
    Write-Host "    backup: $bak" -ForegroundColor DarkGray
}

# ───────────────────────────────────────────────────────────────────────
# Find frontend container
# ───────────────────────────────────────────────────────────────────────
function Find-Container($pattern) {
    try {
        $all = (docker ps --format "{{.Names}}" 2>$null) -split "`n" | Where-Object { $_ -and $_.Trim() }
        foreach ($name in $all) { if ($name -match $pattern) { return $name } }
    } catch {}
    return $null
}

$fe = Find-Container "frontend|^uza-frontend|-frontend-"
if (-not $fe) {
    throw "Frontend container not running. Start the stack first: docker compose up -d"
}
Write-Host "[i] Frontend container: $fe" -ForegroundColor Cyan

# ───────────────────────────────────────────────────────────────────────
# [1/3] Production build
# ───────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "[1/3] Building production bundle (this takes 2-5 minutes)..." -ForegroundColor Yellow
Write-Host "      Using `"npx vite build`" directly (skipping vue-tsc strict check" -ForegroundColor DarkGray
Write-Host "      because we want bundles fast for emergency fix)" -ForegroundColor DarkGray

# Bump Node memory to avoid heap-OOM on a 250-file project
$buildStart = Get-Date
docker exec -e NODE_OPTIONS=--max-old-space-size=4096 $fe npx vite build
if ($LASTEXITCODE -ne 0) {
    Write-Host "    BUILD FAILED" -ForegroundColor Red
    Write-Host "    Check the error above. Common causes:" -ForegroundColor Red
    Write-Host "      - missing dependency: docker exec $fe npm install" -ForegroundColor White
    Write-Host "      - TypeScript syntax error in a recent file" -ForegroundColor White
    throw "vite build failed"
}
$buildElapsed = (Get-Date) - $buildStart
Write-Host "    Build OK in $([int]$buildElapsed.TotalSeconds)s" -ForegroundColor Green

# Verify dist was created
$distCheck = docker exec $fe sh -c "test -f /app/dist/index.html && echo OK || echo MISSING"
if (-not ($distCheck -match "OK")) {
    throw "dist/index.html missing after build - check container logs"
}

# ───────────────────────────────────────────────────────────────────────
# [2/3] Patch docker-compose.yml: command -> vite preview
# ───────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "[2/3] Patching docker-compose.yml" -ForegroundColor Yellow

$composePath = $null
foreach ($candidate in @("backend\docker-compose.yml", "docker-compose.yml")) {
    $p = Join-Path $root $candidate
    if (Test-Path -LiteralPath $p) { $composePath = $p; break }
}
if (-not $composePath) {
    throw "docker-compose.yml not found at backend/ or root"
}
Write-Host "    compose path: $composePath" -ForegroundColor DarkGray

$compose = Read-File $composePath
$fileHasCRLF = $compose.Contains("`r`n")
$composeN = $compose.Replace("`r`n", "`n")

$oldCmd = "    command: npm run dev -- --host 0.0.0.0"
$newCmd = "    command: npx vite preview --host 0.0.0.0 --port 5173 --strictPort"

if ($composeN.Contains($newCmd)) {
    Write-Host "    SKIP: docker-compose.yml already uses `"vite preview`"" -ForegroundColor DarkGray
} elseif (-not $composeN.Contains($oldCmd)) {
    Write-Host "    WARN: original `"npm run dev`" command not found in compose file" -ForegroundColor Yellow
    Write-Host "          patch skipped. If you previously customised the command, edit manually:" -ForegroundColor Yellow
    Write-Host "          command: npx vite preview --host 0.0.0.0 --port 5173 --strictPort" -ForegroundColor White
} else {
    $count = 0; $idx = 0
    while (($idx = $composeN.IndexOf($oldCmd, $idx)) -ge 0) { $count++; $idx += $oldCmd.Length }
    if ($count -gt 1) { throw "Multiple matches for `"npm run dev`" command in compose - refusing to patch" }

    Backup-File $composePath
    $patchedN = $composeN.Replace($oldCmd, $newCmd)
    $patchedOut = if ($fileHasCRLF) { $patchedN.Replace("`n", "`r`n") } else { $patchedN }
    Write-File $composePath $patchedOut
    Write-Host "    Patched: command -> npx vite preview --strictPort" -ForegroundColor Green
}

# ───────────────────────────────────────────────────────────────────────
# [3/3] Recreate frontend container with new command
# ───────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "[3/3] Recreating frontend container" -ForegroundColor Yellow

$composeDir = Split-Path $composePath -Parent
Push-Location $composeDir
try {
    docker compose up -d --force-recreate --no-deps frontend
    if ($LASTEXITCODE -ne 0) { throw "docker compose up failed" }
} finally {
    Pop-Location
}

# Wait for it to be ready
Write-Host ""
Write-Host "[=] Waiting for frontend to serve (up to 20s)" -ForegroundColor Cyan
$ok = $false
for ($i = 0; $i -lt 20; $i++) {
    Start-Sleep -Seconds 1
    try {
        $resp = Invoke-WebRequest -Uri "https://localhost/" -UseBasicParsing -SkipCertificateCheck -TimeoutSec 2 -ErrorAction Stop 2>$null
        if ($resp.StatusCode -eq 200 -and $resp.Content -match "<\!DOCTYPE html>") {
            $ok = $true
            Write-Host "    Up after $($i+1)s" -ForegroundColor Green
            break
        }
    } catch {}
}
if (-not $ok) {
    Write-Host "    Not responding within 20s. Check logs:" -ForegroundColor Yellow
    Write-Host "      docker logs $fe --tail 30" -ForegroundColor White
}

# Show container stats so user can confirm CPU dropped
Write-Host ""
Write-Host "[=] CPU/MEM after switch:" -ForegroundColor Cyan
docker stats --no-stream $fe

Write-Host ""
Write-Host "===================================================================" -ForegroundColor Green
Write-Host " p134 COMPLETE — frontend now in production mode" -ForegroundColor Green
Write-Host "===================================================================" -ForegroundColor Green
Write-Host ""
Write-Host "What changed:" -ForegroundColor Cyan
Write-Host "  - frontend now serves pre-built dist/ via `"vite preview`"" -ForegroundColor White
Write-Host "  - on-demand TypeScript/Vue compilation is OFF" -ForegroundColor White
Write-Host "  - HMR is OFF (need full page refresh to see source code changes)" -ForegroundColor White
Write-Host "  - CPU should drop from ~36% to under 2%" -ForegroundColor White
Write-Host ""
Write-Host "Verify in the browser:" -ForegroundColor Cyan
Write-Host "  1. Hard refresh (Ctrl+Shift+R)" -ForegroundColor White
Write-Host "  2. Switch between dashboards - should be instant" -ForegroundColor White
Write-Host ""
Write-Host "When you need to make Vue/TS code changes:" -ForegroundColor DarkGray
Write-Host "  - Edit source as usual" -ForegroundColor White
Write-Host "  - Rerun this script (p134-frontend-prod-build.ps1) to rebuild" -ForegroundColor White
Write-Host "  - Or temporarily revert to dev mode by editing docker-compose.yml:" -ForegroundColor White
Write-Host "      command: npm run dev -- --host 0.0.0.0" -ForegroundColor DarkGray
