# =====================================================================
# p137-perms-and-dropdown-style.ps1
# =====================================================================
# Three fixes in one pass:
#
# 1. CRITICAL: backend RBAC — "bp.view required" / "kpi.view required"
#    errors for users who DO have access. Bug: _has_permission looked at
#    user.role (singular), but the model field is user.roles (list).
#    hasattr(user,"role")=False -> role_code=None -> admin/ceo bypass
#    never triggers. Fix: iterate user.roles + check roles[*].permissions.
#
# 2. InvestProjects dropdown bug — items rendered inline (glued in row).
#    Fix: inline styles directly on template, no CSS dependency.
#
# 3. CreditPortfolio CompanyDropdown — restyle trigger to glass-navy.
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
    $bak = "$path.bakP137.$stamp"
    Copy-Item -LiteralPath $path -Destination $bak -Force
    Write-Host "    backup: $bak" -ForegroundColor DarkGray
    $patchedN = $srcN.Replace($oldN, $newN)
    if ($fileHasCRLF) { $out = $patchedN.Replace("`n", "`r`n") } else { $out = $patchedN }
    Write-File $path $out
    Write-Host "    OK" -ForegroundColor Green
}

$bpRoute  = Join-Path $root "backend\app\api\routes\business_plan.py"
$kpiRoute = Join-Path $root "backend\app\api\routes\kpi.py"
$invPath  = Join-Path $root "frontend\src\views\InvestProjects.vue"
$cpDd     = Join-Path $root "frontend\src\components\CreditPortfolio\CompanyDropdown.vue"

# ───────────────────────────────────────────────────────────────────────
# [1/4] backend business_plan.py
# ───────────────────────────────────────────────────────────────────────
$bpOld = @'
def _has_permission(user: User, code: str) -> bool:
    if not user:
        return False
    # Role-based bypass FIRST — admin/ceo always have access regardless of
    # individual permission_codes assignment.
    role_code = getattr(user.role, "code", None) if hasattr(user, "role") else None
    if role_code in ("admin", "ceo"):
        return True
    # Owner email bypass (platform owner v.kim@uz-assets.uz has full access).
    if getattr(user, "email", "") == "v.kim@uz-assets.uz":
        return True
    perms = getattr(user, "permission_codes", None)
    if perms:
        return code in perms
    if role_code in ("debt", "readonly", "imv_admin") and code == "bp.view":
        return True
    return False
'@
$bpNew = @'
def _has_permission(user: User, code: str) -> bool:
    """Pack 137: fixed — was reading user.role (single, does not exist)
    instead of user.roles (list). Now iterates all roles + checks
    role.permissions if SQLAlchemy relationship is loaded.
    """
    if not user:
        return False
    if getattr(user, "is_owner", False):
        return True
    if getattr(user, "email", "") == "v.kim@uz-assets.uz":
        return True
    roles = getattr(user, "roles", None) or []
    for r in roles:
        rcode = getattr(r, "code", "") or ""
        if rcode in ("admin", "ceo"):
            return True
        if rcode in ("debt", "readonly", "imv_admin") and code == "bp.view":
            return True
        for p in (getattr(r, "permissions", None) or []):
            if getattr(p, "code", "") == code:
                return True
    perms = getattr(user, "permission_codes", None)
    if perms and code in perms:
        return True
    return False
'@
Apply-Patch $bpRoute $bpOld $bpNew "[1/4] backend business_plan.py: fix _has_permission"

# ───────────────────────────────────────────────────────────────────────
# [2/4] backend kpi.py
# ───────────────────────────────────────────────────────────────────────
$kpiOld = @'
def _has_permission(user: User, code: str) -> bool:
    if not user:
        return False
    # Role-based bypass FIRST — admin/ceo always have access regardless of
    # individual permission_codes assignment.
    role_code = getattr(user.role, "code", None) if hasattr(user, "role") else None
    if role_code in ("admin", "ceo"):
        return True
    # Owner email bypass (platform owner v.kim@uz-assets.uz has full access).
    if getattr(user, "email", "") == "v.kim@uz-assets.uz":
        return True
    perms = getattr(user, "permission_codes", None)
    if perms:
        return code in perms
    if role_code in ("debt", "readonly", "imv_admin") and code == "kpi.view":
        return True
    return False
'@
$kpiNew = @'
def _has_permission(user: User, code: str) -> bool:
    """Pack 137: same fix as business_plan.py — iterate user.roles."""
    if not user:
        return False
    if getattr(user, "is_owner", False):
        return True
    if getattr(user, "email", "") == "v.kim@uz-assets.uz":
        return True
    roles = getattr(user, "roles", None) or []
    for r in roles:
        rcode = getattr(r, "code", "") or ""
        if rcode in ("admin", "ceo"):
            return True
        if rcode in ("debt", "readonly", "imv_admin") and code == "kpi.view":
            return True
        for p in (getattr(r, "permissions", None) or []):
            if getattr(p, "code", "") == code:
                return True
    perms = getattr(user, "permission_codes", None)
    if perms and code in perms:
        return True
    return False
'@
Apply-Patch $kpiRoute $kpiOld $kpiNew "[2/4] backend kpi.py: fix _has_permission"

# ───────────────────────────────────────────────────────────────────────
# [3/4] InvestProjects popover — inline styles
# ───────────────────────────────────────────────────────────────────────
$ipOld = @"
        <div v-if="companyDdOpen" class="ip-co-pop" @click.stop>
          <button
            v-for="co in availableCompanies"
            :key="co"
            class="ip-co-pop-item"
            :class="{ on: co === selectedCompany }"
            @click="pickCompany(co)"
          >
            <span class="ip-co-pop-dot" :style="{ background: co === selectedCompany ? '#9B8EC4' : '#D1D5DB' }"></span>
            <span class="ip-co-pop-name">{{ co }}</span>
            <svg v-if="co === selectedCompany" width="10" height="10" viewBox="0 0 12 12" fill="none" stroke="#1D9E75" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="2 6 5 9 10 3"/></svg>
          </button>
        </div>
"@
$ipNew = @"
        <div
          v-if="companyDdOpen"
          class="ip-co-pop"
          @click.stop
          style="position:absolute; top:44px; left:56px; z-index:100; min-width:240px; background:#1E2A4A; border:1px solid rgba(255,255,255,.12); border-radius:10px; padding:4px; display:flex; flex-direction:column; gap:1px; box-shadow:0 12px 32px rgba(15,23,60,.4), 0 4px 12px rgba(15,23,60,.2);"
        >
          <button
            v-for="co in availableCompanies"
            :key="co"
            class="ip-co-pop-item"
            :class="{ on: co === selectedCompany }"
            @click="pickCompany(co)"
            :style="{
              display: 'flex',
              alignItems: 'center',
              gap: '9px',
              padding: '8px 11px',
              background: co === selectedCompany ? 'rgba(155,142,196,.18)' : 'transparent',
              border: 'none',
              color: '#fff',
              fontSize: '12px',
              fontWeight: '500',
              cursor: 'pointer',
              borderRadius: '6px',
              textAlign: 'left',
              width: '100%',
            }"
          >
            <span :style="{ width: '7px', height: '7px', borderRadius: '50%', flexShrink: 0, background: co === selectedCompany ? '#9B8EC4' : '#D1D5DB' }"></span>
            <span style="flex:1; text-align:left;">{{ co }}</span>
            <svg v-if="co === selectedCompany" width="10" height="10" viewBox="0 0 12 12" fill="none" stroke="#1D9E75" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="2 6 5 9 10 3"/></svg>
          </button>
        </div>
"@
Apply-Patch $invPath $ipOld $ipNew "[3/4] InvestProjects: popover inline styles"

# ───────────────────────────────────────────────────────────────────────
# [4/4] CreditPortfolio CompanyDropdown trigger restyle
# ───────────────────────────────────────────────────────────────────────
$cpOld = @'
/* ─── Trigger ─── */
.cp-dd-btn {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  background: rgba(15, 18, 40, 0.86);
  color: rgba(255, 255, 255, 0.92);
  border: 1px solid rgba(250, 199, 117, 0.18);
  border-radius: 10px;
  cursor: pointer;
  font-family: inherit;
  text-align: left;
  min-width: 240px;
  transition: border-color 0.18s, background 0.18s;
}

.cp-dd-btn:hover,
.cp-dd-btn-open {
  border-color: rgba(250, 199, 117, 0.4);
  background: rgba(15, 18, 40, 0.96);
}

.cp-dd-label {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.cp-dd-name {
  font-size: 13px;
  font-weight: 500;
  color: rgba(255, 255, 255, 0.92);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.cp-dd-sub {
  font-size: 10px;
  font-weight: 500;
  color: rgba(250, 199, 117, 0.75);
  letter-spacing: 0.04em;
  font-feature-settings: "tnum";
}
'@
$cpNew = @'
/* ─── Trigger (Pack 137 restyle — glass-navy like InvestProjects/FinModel) ─── */
.cp-dd-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 11px;
  height: 32px;
  background: rgba(255, 255, 255, 0.08);
  color: #fff;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 8px;
  cursor: pointer;
  font-family: inherit;
  font-size: 12px;
  font-weight: 500;
  text-align: left;
  min-width: 180px;
  transition: background 0.15s, border-color 0.15s;
}

.cp-dd-btn:hover,
.cp-dd-btn-open {
  background: rgba(255, 255, 255, 0.14);
  border-color: rgba(255, 255, 255, 0.22);
}

.cp-dd-label {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}

.cp-dd-name {
  font-size: 12px;
  font-weight: 500;
  color: #fff;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: 1.2;
}

.cp-dd-sub {
  font-size: 9.5px;
  font-weight: 500;
  color: rgba(255, 255, 255, 0.55);
  letter-spacing: 0.06em;
  font-feature-settings: "tnum";
  text-transform: uppercase;
}
'@
Apply-Patch $cpDd $cpOld $cpNew "[4/4] CreditPortfolio CompanyDropdown: glass-trigger restyle"

# ───────────────────────────────────────────────────────────────────────
# Verify + rebuild + restart
# ───────────────────────────────────────────────────────────────────────
function Find-Container($pattern) {
    $all = (docker ps --format "{{.Names}}" 2>$null) -split "`n" | Where-Object { $_ -and $_.Trim() }
    foreach ($name in $all) { if ($name -match $pattern) { return $name } }
    return $null
}
$bk = Find-Container "backend|^uza-backend"
$fe = Find-Container "frontend|^uza-frontend"

if ($bk) {
    Write-Host ""
    Write-Host "[=] Verifying backend syntax + restarting" -ForegroundColor Cyan
    docker exec $bk python -m py_compile /app/app/api/routes/business_plan.py /app/app/api/routes/kpi.py
    if ($LASTEXITCODE -ne 0) { throw "backend py_compile failed" }
    docker restart $bk | Out-Null
    Write-Host "    backend restarted" -ForegroundColor Green
}
if ($fe) {
    Write-Host ""
    Write-Host "[=] Rebuilding frontend" -ForegroundColor Cyan
    docker exec $fe sh -c "rm -rf /app/dist /app/node_modules/.vite 2>/dev/null; true"
    docker exec -e NODE_OPTIONS=--max-old-space-size=4096 -e VITE_API_BASE_URL= $fe npx vite build
    if ($LASTEXITCODE -ne 0) { throw "vite build failed" }
    docker restart $fe | Out-Null
    Write-Host "    frontend restarted" -ForegroundColor Green
}

Write-Host ""
Write-Host "===================================================================" -ForegroundColor Green
Write-Host " p137 COMPLETE" -ForegroundColor Green
Write-Host "===================================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Test:" -ForegroundColor Cyan
Write-Host "  1. Colleague reloads Business Plan and KPI - 403 should be gone" -ForegroundColor White
Write-Host "  2. /invest-projects - dropdown items in a column" -ForegroundColor White
Write-Host "  3. /credit-portfolio - All companies button glass-navy" -ForegroundColor White
