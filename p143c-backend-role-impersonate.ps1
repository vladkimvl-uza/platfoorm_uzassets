# =====================================================================
# p143c-backend-role-impersonate.ps1   (RBAC v3 session 4 - part 3)
# =====================================================================
# Backend additions to complete RBAC v3:
#
# 1. POST   /rbac/roles                 -> create custom (non-system) role
# 2. DELETE /rbac/roles/{code}          -> delete role (FK-checked)
# 3. PATCH  /rbac/roles/{code}          -> update name/description (system roles can be edited too)
# 4. POST   /rbac/users/{id}/preview-token  -> 30-min impersonate token
#
# All write endpoints emit audit_log entries.
# All require admin role bypass (or `admin.users` permission).
# preview-token endpoint also requires `admin.users`.
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
        Write-Host "    SKIP: already applied" -ForegroundColor DarkGray; return
    }
    if (-not $srcN.Contains($oldN)) { throw "Anchor NOT FOUND in $label" }
    $c = 0; $i = 0
    while (($i = $srcN.IndexOf($oldN, $i)) -ge 0) { $c++; $i += $oldN.Length }
    if ($c -gt 1) { throw "Anchor NOT UNIQUE ($c) in $label" }
    Copy-Item -LiteralPath $path -Destination "$path.bakP143c.$stamp" -Force
    Write-Host "    backup: $path.bakP143c.$stamp" -ForegroundColor DarkGray
    $patched = $srcN.Replace($oldN, $newN)
    if ($hasCRLF) { $out = $patched.Replace("`n", "`r`n") } else { $out = $patched }
    Write-File $path $out
    Write-Host "    OK" -ForegroundColor Green
}

$be = "backend\app"

# ───────────────────────────────────────────────────────────────────────
# [1/3] schemas/rbac.py — add RoleCreate / RoleUpdate / PreviewTokenResponse
# ───────────────────────────────────────────────────────────────────────
$oldSchema = @'
class RoleByEmailRule(BaseModel):
'@
$newSchema = @'
class RoleCreatePayload(BaseModel):
    code: str = Field(..., min_length=2, max_length=64, pattern=r"^[a-z][a-z0-9_]*$",
                       description="Lowercase slug, snake_case (e.g. mining_lead)")
    name_ru: str = Field(..., min_length=1, max_length=255)
    name_en: Optional[str] = Field(None, max_length=255)
    description_ru: Optional[str] = Field(None, max_length=512)
    sort_order: int = Field(100, ge=0, le=9999)
    permission_codes: List[str] = Field(default_factory=list)


class RoleUpdatePayload(BaseModel):
    name_ru: Optional[str] = Field(None, min_length=1, max_length=255)
    name_en: Optional[str] = Field(None, max_length=255)
    description_ru: Optional[str] = Field(None, max_length=512)
    sort_order: Optional[int] = Field(None, ge=0, le=9999)


class PreviewTokenResponse(BaseModel):
    """Pack 143c: short-lived access token to view UI as another user (impersonate)."""
    access_token: str
    expires_in: int                       # seconds
    target_user_id: UUID
    target_email: str


class RoleByEmailRule(BaseModel):
'@
Apply-Patch (Join-Path $root "$be\schemas\rbac.py") $oldSchema $newSchema "[1/3] schemas/rbac.py: add RoleCreate/RoleUpdate/PreviewToken"

# ───────────────────────────────────────────────────────────────────────
# [2/3] api/routes/rbac.py — add POST/DELETE/PATCH roles + preview-token
# ───────────────────────────────────────────────────────────────────────

# 2a. Extend imports
$oldImp = @'
    RoleByEmailRule, RoleDetail, UserBrief, UserCreatePayload, UserDetail,
'@
$newImp = @'
    PreviewTokenResponse, RoleByEmailRule, RoleCreatePayload, RoleDetail,
    RoleUpdatePayload, UserBrief, UserCreatePayload, UserDetail,
'@
Apply-Patch (Join-Path $root "$be\api\routes\rbac.py") $oldImp $newImp "[2a/3] rbac.py: extend imports"

# 2b. Insert new role endpoints + preview-token after update_role_permissions
$oldAnchor = @'
    return await get_role(code, db, user)


# =====================================================================
# Users
# =====================================================================
'@
$newBlock = @'
    return await get_role(code, db, user)


# ─── Pack 143c: create / update / delete role + impersonate ────────────

@router.post("/roles", response_model=RoleDetail, status_code=http_status.HTTP_201_CREATED)
async def create_role(
    payload: RoleCreatePayload,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Create a custom (non-system) role with optional initial permissions."""
    _require_admin(user)

    # Duplicate check
    existing_q = await db.execute(select(Role).where(Role.code == payload.code))
    if existing_q.scalar_one_or_none():
        raise HTTPException(http_status.HTTP_409_CONFLICT, f"Role '{payload.code}' already exists")

    # Validate permission codes if provided
    perm_objs: list[Permission] = []
    if payload.permission_codes:
        pq = await db.execute(select(Permission).where(Permission.code.in_(payload.permission_codes)))
        perm_objs = list(pq.scalars().all())
        missing = set(payload.permission_codes) - {p.code for p in perm_objs}
        if missing:
            raise HTTPException(http_status.HTTP_400_BAD_REQUEST,
                                f"Unknown permission codes: {sorted(missing)}")

    role = Role(
        code=payload.code,
        name_ru=payload.name_ru,
        name_en=payload.name_en,
        description_ru=payload.description_ru,
        sort_order=payload.sort_order,
        is_system=False,
    )
    db.add(role)
    await db.flush()

    for p in perm_objs:
        await db.execute(role_permission.insert().values(role_id=role.id, permission_id=p.id))
    await db.commit()

    await append_audit_entry(
        db, actor_id=str(user.id), actor_email=user.email,
        action="rbac.role.create",
        entity_type="role", entity_id=str(role.id),
        notes=f"role={role.code}, permissions={len(perm_objs)}",
    )
    await db.commit()

    return await get_role(role.code, db, user)


@router.patch("/roles/{code}", response_model=RoleDetail)
async def update_role(
    code: str,
    payload: RoleUpdatePayload,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Update role's display fields (name, description, sort_order).

    System roles CAN be edited (name/description) — only their `code`
    and `is_system` flag are immutable, and they cannot be deleted.
    """
    _require_admin(user)
    rq = await db.execute(select(Role).where(Role.code == code))
    role = rq.scalar_one_or_none()
    if not role:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, f"Role '{code}' not found")

    changed: list[str] = []
    if payload.name_ru is not None and payload.name_ru != role.name_ru:
        role.name_ru = payload.name_ru; changed.append("name_ru")
    if payload.name_en is not None and payload.name_en != role.name_en:
        role.name_en = payload.name_en; changed.append("name_en")
    if payload.description_ru is not None and payload.description_ru != role.description_ru:
        role.description_ru = payload.description_ru; changed.append("description_ru")
    if payload.sort_order is not None and payload.sort_order != role.sort_order:
        role.sort_order = payload.sort_order; changed.append("sort_order")

    if changed:
        await db.commit()
        await append_audit_entry(
            db, actor_id=str(user.id), actor_email=user.email,
            action="rbac.role.update",
            entity_type="role", entity_id=str(role.id),
            notes=f"role={code}, fields={','.join(changed)}",
        )
        await db.commit()

    return await get_role(code, db, user)


@router.delete("/roles/{code}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_role(
    code: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Delete a non-system role. Fails if any users still have this role."""
    _require_admin(user)
    rq = await db.execute(select(Role).where(Role.code == code))
    role = rq.scalar_one_or_none()
    if not role:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, f"Role '{code}' not found")
    if role.is_system:
        raise HTTPException(http_status.HTTP_400_BAD_REQUEST,
                            f"System role '{code}' cannot be deleted")

    # FK check — refuse if any users still hold this role
    from app.models.user import user_role as user_role_table
    uq = await db.execute(
        select(func.count()).select_from(user_role_table).where(user_role_table.c.role_id == role.id)
    )
    user_count = int(uq.scalar() or 0)
    if user_count > 0:
        raise HTTPException(
            http_status.HTTP_409_CONFLICT,
            f"Cannot delete role '{code}': {user_count} user(s) still assigned. "
            f"Reassign them first.",
        )

    # Clean up role_permission links
    await db.execute(delete(role_permission).where(role_permission.c.role_id == role.id))
    role_id = str(role.id)
    await db.delete(role)
    await db.commit()

    await append_audit_entry(
        db, actor_id=str(user.id), actor_email=user.email,
        action="rbac.role.delete",
        entity_type="role", entity_id=role_id,
        notes=f"role={code}",
    )
    await db.commit()
    return


@router.post("/users/{user_id}/preview-token", response_model=PreviewTokenResponse)
async def create_preview_token(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Issue a 30-minute impersonate token to view the platform as another user.

    The resulting token contains the target user's id as `sub` plus an
    `impersonator_id` claim — audit middleware logs that the actor is
    impersonating. The token is NOT a refresh token; it expires hard in 30 min.

    The actor must be an admin (full bypass) or have the `admin.users` permission.
    Cannot impersonate yourself or another admin (security).
    """
    _require_admin(user)

    target_q = await db.execute(select(User).where(User.id == user_id))
    target = target_q.scalar_one_or_none()
    if not target:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "User not found")
    if str(target.id) == str(user.id):
        raise HTTPException(http_status.HTTP_400_BAD_REQUEST,
                            "Cannot impersonate yourself")
    if not target.is_active:
        raise HTTPException(http_status.HTTP_400_BAD_REQUEST,
                            "Cannot impersonate inactive user")

    # Refuse impersonating another admin / owner for safety
    from app.models.user import user_role as user_role_table
    rq = await db.execute(
        select(Role.code)
        .join(user_role_table, user_role_table.c.role_id == Role.id)
        .where(user_role_table.c.user_id == target.id)
    )
    target_role_codes = [r for (r,) in rq.all()]
    if target.is_owner or "admin" in target_role_codes:
        raise HTTPException(http_status.HTTP_403_FORBIDDEN,
                            "Cannot impersonate an admin or owner")

    from app.core.jwt import create_access_token
    expires_minutes = 30
    token = create_access_token(
        subject=str(target.id),
        expires_minutes=expires_minutes,
        extra_claims={
            "impersonator_id": str(user.id),
            "impersonator_email": user.email,
            "is_preview": True,
        },
    )

    await append_audit_entry(
        db, actor_id=str(user.id), actor_email=user.email,
        action="rbac.user.impersonate",
        entity_type="user", entity_id=str(target.id),
        notes=f"target_email={target.email}, duration_min={expires_minutes}",
    )
    await db.commit()

    return PreviewTokenResponse(
        access_token=token,
        expires_in=expires_minutes * 60,
        target_user_id=target.id,
        target_email=target.email,
    )


# =====================================================================
# Users
# =====================================================================
'@
Apply-Patch (Join-Path $root "$be\api\routes\rbac.py") $oldAnchor $newBlock "[2b/3] rbac.py: insert new role + preview-token endpoints"

# 2c. Ensure imports exist (delete, func)
$rbacPath = Join-Path $root "$be\api\routes\rbac.py"
$rbacSrc = Read-File $rbacPath
if (-not ($rbacSrc -match 'from sqlalchemy import.*\bfunc\b')) {
    # Find existing sqlalchemy import and add func
    Apply-Patch $rbacPath `
        'from sqlalchemy import delete, select' `
        'from sqlalchemy import delete, func, select' `
        "[2c/3] rbac.py: add func import"
}

# ───────────────────────────────────────────────────────────────────────
# [3/3] Restart backend
# ───────────────────────────────────────────────────────────────────────
function Find-Container($pattern) {
    $all = (docker ps --format "{{.Names}}" 2>$null) -split "`n" | Where-Object { $_ -and $_.Trim() }
    foreach ($name in $all) { if ($name -match $pattern) { return $name } }
    return $null
}
$bec = Find-Container "backend|^uza-backend"
if (-not $bec) {
    Write-Host "[!] Backend container not running" -ForegroundColor Yellow
} else {
    Write-Host ""
    Write-Host "[=] Restarting backend" -ForegroundColor Cyan
    docker restart $bec | Out-Null
    Write-Host "    waiting for health..." -ForegroundColor DarkGray
    Start-Sleep -Seconds 4
    docker logs $bec --tail 20 2>&1 | Select-String -Pattern "Application startup|Uvicorn|ERROR" | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }
    Write-Host "    backend restarted" -ForegroundColor Green
}

Write-Host ""
Write-Host "===================================================================" -ForegroundColor Green
Write-Host " p143c COMPLETE - Backend endpoints added" -ForegroundColor Green
Write-Host "===================================================================" -ForegroundColor Green
Write-Host ""
Write-Host "New backend endpoints (test via Swagger /docs):" -ForegroundColor Cyan
Write-Host "  POST   /rbac/roles                     - create custom role" -ForegroundColor White
Write-Host "  PATCH  /rbac/roles/{code}              - update name/description" -ForegroundColor White
Write-Host "  DELETE /rbac/roles/{code}              - delete role (FK-checked)" -ForegroundColor White
Write-Host "  POST   /rbac/users/{id}/preview-token  - 30-min impersonate token" -ForegroundColor White
Write-Host ""
Write-Host "All emit audit_log entries (visible in RBAC v3 -> Аудит tab)" -ForegroundColor DarkGray
Write-Host ""
Write-Host "Next (p143d): wire these into RolesPage UI buttons + impersonate" -ForegroundColor DarkGray
Write-Host "  in UserDetailDrawer ('Войти как этот пользователь')" -ForegroundColor DarkGray
