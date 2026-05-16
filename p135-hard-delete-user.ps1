# =====================================================================
# p135-hard-delete-user.ps1   (RBAC v2: permanent user deletion)
# =====================================================================
# Adds the ability to PERMANENTLY remove a user from the database
# (not just deactivate). Existing DELETE /rbac/users/{id} is soft-delete
# (is_active=false). New endpoint is DELETE /rbac/users/{id}/permanent.
#
# Safety: ALL foreign keys pointing at users already have ondelete=CASCADE
# (mfa_login_challenge, telegram_outbox, user_telegram_pref, user_role,
#  api_keys, ai_conversation, moderation_submissions etc.) or SET NULL
# (assigned_to in tasks, created_by in projects, etc.). Postgres handles
# the cascade atomically. A single DELETE statement is sufficient.
#
# Frontend: red "Удалить навсегда" button + confirm dialog requiring
# the admin to TYPE THE USER'S EMAIL exactly — prevents accidental clicks.
# Hidden if user is owner OR the target is themselves.
#
# 5 patches:
#   [1] backend rbac.py: new endpoint DELETE /users/{id}/permanent
#   [2] frontend api/rbac.ts: permanentlyDeleteUser method
#   [3] RBACMatrix.vue script: refs + submitPermanentDelete fn
#   [4] RBACMatrix.vue template: button + inline confirm with email gate
#   [5] RBACMatrix.vue style: dark-red confirm block CSS
# =====================================================================

$ErrorActionPreference = "Stop"
$enc = New-Object System.Text.UTF8Encoding($false)
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$root = $PSScriptRoot
if (-not $root) { $root = (Get-Location).Path }

function Read-File($p)  { return [System.IO.File]::ReadAllText($p, $enc) }
function Write-File($p, $text) { [System.IO.File]::WriteAllText($p, $text, $enc) }
function Backup-File($p) {
    $bak = "$p.bakP135.$stamp"
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

$rbacBack = Join-Path $root "backend\app\api\routes\rbac.py"
$rbacApi  = Join-Path $root "frontend\src\api\rbac.ts"
$matrix   = Join-Path $root "frontend\src\views\RBACMatrix.vue"

# ───────────────────────────────────────────────────────────────────────
# [1/5] backend: DELETE /rbac/users/{id}/permanent
# ───────────────────────────────────────────────────────────────────────
$old1 = @"
    u.is_active = False
    await db.commit()

    await append_audit_entry(
        db, actor_id=str(user.id), actor_email=user.email,
        action="rbac.user.deactivate",
        entity_type="user", entity_id=str(u.id),
        notes=f"target={u.email}",
    )
"@
$new1 = @"
    u.is_active = False
    await db.commit()

    await append_audit_entry(
        db, actor_id=str(user.id), actor_email=user.email,
        action="rbac.user.deactivate",
        entity_type="user", entity_id=str(u.id),
        notes=f"target={u.email}",
    )


# ── Hard delete (Pack 135) ────────────────────────────────────────────

@router.delete("/users/{user_id}/permanent", status_code=http_status.HTTP_204_NO_CONTENT)
async def permanently_delete_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Permanently remove a user from the database.

    All FKs referencing users have ondelete=CASCADE (owned data: mfa
    challenges, outbox, prefs, user_role junction, api_keys, ai sessions,
    moderation submissions where user = author) or ondelete=SET NULL
    (references: assignee_id, reviewer_id, created_by_id etc.), so a
    single DELETE statement removes the user atomically.

    Safety guards:
      - admin only (_require_admin)
      - cannot delete owner
      - cannot delete self
    """
    _require_admin(user)

    u_q = await db.execute(select(User).where(User.id == user_id))
    u = u_q.scalar_one_or_none()
    if not u:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "User not found")

    if u.id == user.id:
        raise HTTPException(
            http_status.HTTP_400_BAD_REQUEST,
            "You cannot delete your own account.",
        )
    if getattr(u, "is_owner", False):
        raise HTTPException(
            http_status.HTTP_400_BAD_REQUEST,
            "Cannot permanently delete the platform owner.",
        )

    target_email = u.email
    target_id = str(u.id)

    await db.delete(u)
    try:
        await db.commit()
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            http_status.HTTP_409_CONFLICT,
            f"Не удалось удалить пользователя: {e.__class__.__name__}. "
            "Возможно, есть связанные данные без CASCADE.",
        )

    await append_audit_entry(
        db, actor_id=str(user.id), actor_email=user.email,
        action="rbac.user.delete_permanent",
        entity_type="user", entity_id=target_id,
        notes=f"target={target_email}",
    )
"@
Apply-Patch $rbacBack $old1 $new1 "[1/5] backend rbac.py: DELETE /users/{id}/permanent"

# ───────────────────────────────────────────────────────────────────────
# [2/5] frontend api/rbac.ts: permanentlyDeleteUser
# ───────────────────────────────────────────────────────────────────────
$old2 = @'
  async deactivateUser(id: string) {
    await api.delete(`/rbac/users/${id}`);
  },
'@
$new2 = @'
  async deactivateUser(id: string) {
    await api.delete(`/rbac/users/${id}`);
  },
  async permanentlyDeleteUser(id: string) {
    await api.delete(`/rbac/users/${id}/permanent`);
  },
'@
Apply-Patch $rbacApi $old2 $new2 "[2/5] api/rbac.ts: permanentlyDeleteUser"

# ───────────────────────────────────────────────────────────────────────
# [3/5] RBACMatrix.vue script: refs + submitPermanentDelete
# ───────────────────────────────────────────────────────────────────────
$old3 = @'
async function submitDeactivate() {
  if (!selectedUserId.value || deactivateSaving.value) return;
  deactivateSaving.value = true;
  error.value = null;
  try {
    await rbacApi.deactivateUser(selectedUserId.value);
    deactivateConfirm.value = false;
    await loadUsers();
    fillProfileFromUser(selectedUserId.value);
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || "Ошибка деактивации";
  } finally {
    deactivateSaving.value = false;
  }
}
'@
$new3 = @'
async function submitDeactivate() {
  if (!selectedUserId.value || deactivateSaving.value) return;
  deactivateSaving.value = true;
  error.value = null;
  try {
    await rbacApi.deactivateUser(selectedUserId.value);
    deactivateConfirm.value = false;
    await loadUsers();
    fillProfileFromUser(selectedUserId.value);
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || "Ошибка деактивации";
  } finally {
    deactivateSaving.value = false;
  }
}

// Pack 135: permanent delete (hard delete from DB)
const permanentDeleteConfirm = ref(false);
const permanentDeleteSaving = ref(false);
const permanentDeleteEmailInput = ref("");
async function submitPermanentDelete() {
  if (!selectedUserId.value || permanentDeleteSaving.value) return;
  if (!effective.value) return;
  if (permanentDeleteEmailInput.value.trim().toLowerCase() !== effective.value.email.toLowerCase()) {
    error.value = "Email не совпадает";
    return;
  }
  permanentDeleteSaving.value = true;
  error.value = null;
  try {
    await rbacApi.permanentlyDeleteUser(selectedUserId.value);
    permanentDeleteConfirm.value = false;
    permanentDeleteEmailInput.value = "";
    selectedUserId.value = null;
    effective.value = null;
    await loadUsers();
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || "Ошибка удаления";
  } finally {
    permanentDeleteSaving.value = false;
  }
}
'@
Apply-Patch $matrix $old3 $new3 "[3/5] RBACMatrix.vue script: permanent-delete refs + handler"

# ───────────────────────────────────────────────────────────────────────
# [4/5] RBACMatrix.vue template: button + inline confirm block with email gate
# ───────────────────────────────────────────────────────────────────────
$old4 = @"
                <button v-if=`"!effective.is_owner && effective.user_id !== auth.user?.id`"
                        class=`"rv-btn rv-btn-red-ghost`" @click=`"deactivateConfirm = true`">
                  <svg width=`"11`" height=`"11`" viewBox=`"0 0 16 16`" fill=`"none`" stroke=`"currentColor`" stroke-width=`"2`" aria-hidden=`"true`">
                    <path d=`"M3 6h10M6 6V3h4v3M5 6v8h6V6`"/>
                  </svg>
                  Деактивировать
                </button>
              </div>
"@
$new4 = @"
                <button v-if=`"!effective.is_owner && effective.user_id !== auth.user?.id`"
                        class=`"rv-btn rv-btn-red-ghost`" @click=`"deactivateConfirm = true`">
                  <svg width=`"11`" height=`"11`" viewBox=`"0 0 16 16`" fill=`"none`" stroke=`"currentColor`" stroke-width=`"2`" aria-hidden=`"true`">
                    <path d=`"M3 6h10M6 6V3h4v3M5 6v8h6V6`"/>
                  </svg>
                  Деактивировать
                </button>
                <button v-if=`"!effective.is_owner && effective.user_id !== auth.user?.id`"
                        class=`"rv-btn rv-btn-red-solid`" @click=`"permanentDeleteConfirm = true`">
                  <svg width=`"11`" height=`"11`" viewBox=`"0 0 16 16`" fill=`"none`" stroke=`"currentColor`" stroke-width=`"2`" aria-hidden=`"true`">
                    <path d=`"M3 4l1 9.5a1.5 1.5 0 0 0 1.5 1.5h5a1.5 1.5 0 0 0 1.5-1.5L13 4M6 4V2.5A.5.5 0 0 1 6.5 2h3a.5.5 0 0 1 .5.5V4M2.5 4h11`"/>
                  </svg>
                  Удалить навсегда
                </button>
              </div>
"@
Apply-Patch $matrix $old4 $new4 "[4a/5] RBACMatrix.vue template: 'Удалить навсегда' button"

$old4b = @"
            <!-- Inline deactivate confirm -->
            <div v-if=`"deactivateConfirm`" class=`"rv-pf-deact`">
              <div class=`"rv-pf-deact-hd`">Деактивировать «{{ effective.email }}»?</div>
              <div class=`"rv-pf-hint`">
                Пользователь не сможет войти. Данные сохраняются — можно активировать обратно через переключатель «Активен».
              </div>
              <div class=`"rv-pf-deact-row`">
                <button class=`"rv-btn rv-btn-ghost`" @click=`"deactivateConfirm = false`">Отмена</button>
                <button class=`"rv-btn rv-btn-red`" :disabled=`"deactivateSaving`" @click=`"submitDeactivate`">
                  {{ deactivateSaving ? `"...`" : `"Деактивировать`" }}
                </button>
              </div>
            </div>
"@
$new4b = @"
            <!-- Inline deactivate confirm -->
            <div v-if=`"deactivateConfirm`" class=`"rv-pf-deact`">
              <div class=`"rv-pf-deact-hd`">Деактивировать «{{ effective.email }}»?</div>
              <div class=`"rv-pf-hint`">
                Пользователь не сможет войти. Данные сохраняются — можно активировать обратно через переключатель «Активен».
              </div>
              <div class=`"rv-pf-deact-row`">
                <button class=`"rv-btn rv-btn-ghost`" @click=`"deactivateConfirm = false`">Отмена</button>
                <button class=`"rv-btn rv-btn-red`" :disabled=`"deactivateSaving`" @click=`"submitDeactivate`">
                  {{ deactivateSaving ? `"...`" : `"Деактивировать`" }}
                </button>
              </div>
            </div>

            <!-- Inline permanent-delete confirm (Pack 135) -->
            <div v-if=`"permanentDeleteConfirm`" class=`"rv-pf-deact rv-pf-perma`">
              <div class=`"rv-pf-deact-hd`">Удалить «{{ effective.email }}» НАВСЕГДА?</div>
              <div class=`"rv-pf-hint rv-pf-hint-warn`">
                Это действие необратимо. Учётная запись и все связанные данные (привязки Telegram, MFA-сессии, конфигурация AI, журналы доступа) будут удалены безвозвратно.
                Назначения задач и проектов будут обнулены.
              </div>
              <div class=`"rv-pf-hint`" style=`"margin-top:8px`">
                Для подтверждения введите email пользователя: <strong>{{ effective.email }}</strong>
              </div>
              <input
                v-model=`"permanentDeleteEmailInput`"
                type=`"text`"
                class=`"rv-pf-perma-input`"
                :placeholder=`"effective.email`"
                autocomplete=`"off`"
              />
              <div class=`"rv-pf-deact-row`">
                <button class=`"rv-btn rv-btn-ghost`" @click=`"permanentDeleteConfirm = false; permanentDeleteEmailInput = ''`">Отмена</button>
                <button
                  class=`"rv-btn rv-btn-red-solid`"
                  :disabled=`"permanentDeleteSaving || permanentDeleteEmailInput.trim().toLowerCase() !== effective.email.toLowerCase()`"
                  @click=`"submitPermanentDelete`"
                >
                  {{ permanentDeleteSaving ? `"...`" : `"Удалить навсегда`" }}
                </button>
              </div>
            </div>
"@
Apply-Patch $matrix $old4b $new4b "[4b/5] RBACMatrix.vue template: permanent-delete confirm block"

# ───────────────────────────────────────────────────────────────────────
# [5/5] RBACMatrix.vue style: red-solid button + perma confirm CSS
# ───────────────────────────────────────────────────────────────────────
$old5 = @'
.rv-pf-deact-hd {
'@
$new5 = @'
/* Pack 135: solid red destructive button + permanent-delete block */
.rv-btn-red-solid {
  background: #B91C1C;
  color: #fff;
  border: 0.5px solid #991B1B;
}
.rv-btn-red-solid:hover:not(:disabled) {
  background: #991B1B;
}
.rv-btn-red-solid:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.rv-pf-perma {
  background: rgba(185,28,28,.04) !important;
  border: 0.5px solid rgba(185,28,28,.3) !important;
}
.rv-pf-perma-input {
  width: 100%;
  margin-top: 8px;
  padding: 8px 10px;
  border: 0.5px solid #D1D5DB;
  border-radius: 6px;
  font-family: ui-monospace, "SF Mono", Menlo, monospace;
  font-size: 12px;
  color: #1E2A4A;
  outline: none;
}
.rv-pf-perma-input:focus {
  border-color: #B91C1C;
  box-shadow: 0 0 0 3px rgba(185,28,28,.12);
}

.rv-pf-deact-hd {
'@
Apply-Patch $matrix $old5 $new5 "[5/5] RBACMatrix.vue style: rv-btn-red-solid + perma block"

# ───────────────────────────────────────────────────────────────────────
# Build + restart (frontend) + restart backend for new endpoint
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
    docker exec $bk python -m py_compile /app/app/api/routes/rbac.py
    if ($LASTEXITCODE -ne 0) { throw "backend syntax check failed" }
    docker restart $bk | Out-Null
    Write-Host "    backend restarted" -ForegroundColor Green
}

if ($fe) {
    Write-Host ""
    Write-Host "[=] Rebuilding frontend bundle" -ForegroundColor Cyan
    docker exec $fe sh -c "rm -rf /app/dist /app/node_modules/.vite 2>/dev/null; true"
    docker exec -e NODE_OPTIONS=--max-old-space-size=4096 -e VITE_API_BASE_URL= $fe npx vite build
    if ($LASTEXITCODE -ne 0) { throw "vite build failed" }
    docker restart $fe | Out-Null
    Write-Host "    frontend restarted" -ForegroundColor Green
}

Write-Host ""
Write-Host "===================================================================" -ForegroundColor Green
Write-Host " p135 COMPLETE - permanent user delete available in RBAC v2" -ForegroundColor Green
Write-Host "===================================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Test:" -ForegroundColor Cyan
Write-Host "  1. Hard refresh (Ctrl+Shift+R)" -ForegroundColor White
Write-Host "  2. Open RBAC v2, select any non-owner user (e.g. tester)" -ForegroundColor White
Write-Host "  3. In actions row you should see a new dark-red button 'Удалить навсегда'" -ForegroundColor White
Write-Host "  4. Click -> confirm block appears -> type the user's email exactly -> Удалить" -ForegroundColor White
Write-Host "  5. User disappears from list. Same email can immediately be reused." -ForegroundColor White
