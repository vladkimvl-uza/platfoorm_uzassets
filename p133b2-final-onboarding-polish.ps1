# =====================================================================
# p133b2-final-onboarding-polish.ps1  (Pack 13.3.2)
# =====================================================================
# Three fixes for the onboarding wizard:
#   1. Step 3 actually sends a 6-digit code to Telegram (the previous flow
#      called /mfa/test-notification which sends a hardcoded text without a
#      code). New backend endpoints:
#        POST /mfa/onboarding/send-code          -> code in TG + challenge_id
#        POST /mfa/onboarding/verify-and-enable  -> verify + activate MFA atomically
#   2. The wizard is now properly centered on wide screens. Replaces the
#      flex:1 + margin:auto chain (which collapses flex column behavior)
#      with a simple width 100% + max-width 980px under align-items center.
#   3. UzaLogo.vue now renders the real PNG logo (640x640) embedded in
#      frontend/public/ instead of the hand-drawn UA monogram SVG.
#
# Files touched:
#   backend/app/api/routes/mfa.py             [3 endpoints appended]
#   frontend/src/api/mfa.ts                    [types + 2 methods]
#   frontend/src/views/MfaOnboarding.vue       [8 patches A-H]
#   frontend/src/components/UzaLogo.vue        [overwrite — img wrapper]
#   frontend/public/uzassets-logo.png          [new — embedded as base64]
#
# Idempotent: each patch detects already-applied state and skips.
#
# Run order: rebuild prod bundle + restart frontend at the end (does both).
# Backend changes require backend container restart — script does NOT restart
# backend automatically since you may want to do it on your own schedule.
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
    $bak = "$p.bakP133b2.$stamp"
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

# Apply-Patch variant that accepts TWO possible old-blocks (idempotent across
# whether p133b1 was applied or not).
function Apply-Patch-EitherOf($path, $oldBlock1, $oldBlock2, $newBlock, $label) {
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
    $old1N = $oldBlock1.Replace("`r`n", "`n")
    $old2N = $oldBlock2.Replace("`r`n", "`n")
    if ($srcN.Contains($old1N)) {
        $chosenOld = $old1N
    } elseif ($srcN.Contains($old2N)) {
        $chosenOld = $old2N
    } else {
        throw "Anchor NOT FOUND (neither variant) in $path ($label)"
    }
    Backup-File $path
    $patchedN = $srcN.Replace($chosenOld, $newN)
    if ($fileHasCRLF) { $patchedOut = $patchedN.Replace("`n", "`r`n") } else { $patchedOut = $patchedN }
    Write-File $path $patchedOut
    Write-Host "    OK" -ForegroundColor Green
}

function Write-Base64-File($path, $b64, $label, [switch]$Overwrite) {
    Write-Host "[*] $label" -ForegroundColor Yellow
    if ((Test-Path -LiteralPath $path) -and (-not $Overwrite)) {
        Write-Host "    SKIP: file already exists" -ForegroundColor DarkGray
        return
    }
    $dir = Split-Path $path -Parent
    if (-not (Test-Path -LiteralPath $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
    $bytes = [Convert]::FromBase64String($b64)
    [System.IO.File]::WriteAllBytes($path, $bytes)
    Write-Host "    OK: $path ($($bytes.Length) bytes)" -ForegroundColor Green
}

$mfaRoute  = Join-Path $root "backend\app\api\routes\mfa.py"
$mfaApi    = Join-Path $root "frontend\src\api\mfa.ts"
$wizPath   = Join-Path $root "frontend\src\views\MfaOnboarding.vue"
$logoVue   = Join-Path $root "frontend\src\components\UzaLogo.vue"
$logoPng   = Join-Path $root "frontend\public\uzassets-logo.png"

# ───────────────────────────────────────────────────────────────────────
# [1/12] backend: append /mfa/onboarding/send-code + /verify-and-enable
# ───────────────────────────────────────────────────────────────────────
$old1 = @"
@router.post("/onboarding/complete", status_code=status.HTTP_204_NO_CONTENT)
async def onboarding_complete(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    current_user.mfa_onboarding_skipped_until = None
    await db.commit()
"@
$new1 = @"
@router.post("/onboarding/complete", status_code=status.HTTP_204_NO_CONTENT)
async def onboarding_complete(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    current_user.mfa_onboarding_skipped_until = None
    await db.commit()


# ── /mfa/onboarding/send-code  + /verify-and-enable  (Pack 13.3.2) ─────

class OnboardingSendCodeOut(_BaseModel):
    challenge_id: str
    ttl_minutes: int


@router.post("/onboarding/send-code", response_model=OnboardingSendCodeOut)
async def onboarding_send_code(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not getattr(current_user, "telegram_chat_id_encrypted", None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Telegram должен быть привязан до отправки кода.",
        )

    from app.models.mfa import MfaLoginChallenge as _Chal, OutboxType as _Out
    code = mfa_service._gen_login_code()
    now = datetime.now(_tz.utc)
    challenge = _Chal(
        user_id=current_user.id,
        code_hashed=mfa_service._hash_bcrypt(code),
        created_at=now,
        expires_at=now + _td(minutes=mfa_service.LOGIN_CODE_TTL_MINUTES),
    )
    db.add(challenge)
    await db.flush()

    await mfa_service.enqueue_telegram_message(
        db, current_user.id, _Out.MFA_CODE,
        payload={
            "code": code,
            "ttl_minutes": mfa_service.LOGIN_CODE_TTL_MINUTES,
            "challenge_id": str(challenge.id),
        },
    )
    await db.commit()
    return OnboardingSendCodeOut(
        challenge_id=str(challenge.id),
        ttl_minutes=mfa_service.LOGIN_CODE_TTL_MINUTES,
    )


class OnboardingVerifyEnableIn(_BaseModel):
    challenge_id: str
    code: str


@router.post("/onboarding/verify-and-enable", response_model=MfaEnableOut)
async def onboarding_verify_and_enable(
    body: OnboardingVerifyEnableIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ok = await mfa_service.verify_login_challenge(db, body.challenge_id, body.code)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Неверный код или срок действия истёк. Запросите код заново.",
        )

    plain_codes = mfa_service.generate_recovery_codes()
    hashed = [mfa_service._hash_bcrypt(c) for c in plain_codes]

    current_user.mfa_enabled = True
    current_user.mfa_method = MfaMethod.TELEGRAM
    current_user.mfa_recovery_codes_hashed = hashed
    current_user.mfa_onboarding_skipped_until = None
    await db.commit()

    return MfaEnableOut(enabled=True, method="telegram", recovery_codes=plain_codes)
"@
Apply-Patch $mfaRoute $old1 $new1 "[1/12] backend mfa.py: send-code + verify-and-enable"

# ───────────────────────────────────────────────────────────────────────
# [2/12] frontend api/mfa.ts: types
# ───────────────────────────────────────────────────────────────────────
$old2 = @'
export interface MfaEnableOut {
  enabled: boolean;
  method: "telegram" | "totp" | "both";
  recovery_codes: string[];
}
'@
$new2 = @'
export interface MfaEnableOut {
  enabled: boolean;
  method: "telegram" | "totp" | "both";
  recovery_codes: string[];
}

export interface MfaOnboardingSendCodeOut {
  challenge_id: string;
  ttl_minutes: number;
}
'@
Apply-Patch $mfaApi $old2 $new2 "[2/12] api/mfa.ts: MfaOnboardingSendCodeOut type"

# ───────────────────────────────────────────────────────────────────────
# [3/12] frontend api/mfa.ts: onboardingSendCode + verifyAndEnable methods
# ───────────────────────────────────────────────────────────────────────
$old3 = @'
  /** Complete MFA login: Telegram code OR recovery code. */
  async verifyMfa(payload: {
    challenge_id?: string;
    code?: string;
    login?: string;
    recovery_code?: string;
  }): Promise<TokenPair> {
    const { data } = await api.post<TokenPair>("/auth/verify-mfa", payload);
    return data;
  },
};
'@
$new3 = @'
  /** Complete MFA login: Telegram code OR recovery code. */
  async verifyMfa(payload: {
    challenge_id?: string;
    code?: string;
    login?: string;
    recovery_code?: string;
  }): Promise<TokenPair> {
    const { data } = await api.post<TokenPair>("/auth/verify-mfa", payload);
    return data;
  },

  // ─── Pack 13.3.2: onboarding code delivery ─────────────────────────

  /** Send a 6-digit code to user's Telegram (during onboarding). */
  async onboardingSendCode(): Promise<MfaOnboardingSendCodeOut> {
    const { data } = await api.post<MfaOnboardingSendCodeOut>("/mfa/onboarding/send-code");
    return data;
  },

  /** Verify the 6-digit code AND enable MFA in one shot. */
  async onboardingVerifyAndEnable(challenge_id: string, code: string): Promise<MfaEnableOut> {
    const { data } = await api.post<MfaEnableOut>("/mfa/onboarding/verify-and-enable", {
      challenge_id, code,
    });
    return data;
  },
};
'@
Apply-Patch $mfaApi $old3 $new3 "[3/12] api/mfa.ts: onboardingSendCode + onboardingVerifyAndEnable"

# ───────────────────────────────────────────────────────────────────────
# [4/12] wizard: add challengeId ref
# ───────────────────────────────────────────────────────────────────────
$old4 = @'
const step = ref<1 | 2 | 3 | 4>(1);
const error = ref<string | null>(null);
const busy = ref(false);
'@
$new4 = @'
const step = ref<1 | 2 | 3 | 4>(1);
const error = ref<string | null>(null);
const busy = ref(false);
const challengeId = ref<string>("");  // Pack 13.3.2: id of the onboarding code challenge
'@
Apply-Patch $wizPath $old4 $new4 "[4/12] wizard: challengeId ref"

# ───────────────────────────────────────────────────────────────────────
# [5/12] wizard: proceedToTestCode -> onboardingSendCode
# ───────────────────────────────────────────────────────────────────────
$old5 = @"
async function proceedToTestCode() {
  step.value = 3;
  codeDigits.value = ["", "", "", "", "", ""];
  codeError.value = null;
  try {
    await mfaApi.testNotification();
  } catch (e: any) {
    codeError.value = "Не удалось отправить тестовый код. Попробуйте «Отправить заново».";
  }
  await nextTick();
  codeInputs.value[0]?.focus();
}
"@
$new5 = @"
async function proceedToTestCode() {
  step.value = 3;
  codeDigits.value = ["", "", "", "", "", ""];
  codeError.value = null;
  try {
    const resp = await mfaApi.onboardingSendCode();
    challengeId.value = resp.challenge_id;
  } catch (e: any) {
    codeError.value = e?.response?.data?.detail || "Не удалось отправить код. Попробуйте «Отправить заново».";
  }
  await nextTick();
  codeInputs.value[0]?.focus();
}
"@
Apply-Patch $wizPath $old5 $new5 "[5/12] wizard: proceedToTestCode sends real code"

# ───────────────────────────────────────────────────────────────────────
# [6/12] wizard: resendTestCode -> onboardingSendCode
# ───────────────────────────────────────────────────────────────────────
$old6 = @"
async function resendTestCode() {
  codeError.value = null;
  try {
    await mfaApi.testNotification();
  } catch (e: any) {
    codeError.value = "Не удалось переотправить код";
  }
}
"@
$new6 = @"
async function resendTestCode() {
  codeError.value = null;
  try {
    const resp = await mfaApi.onboardingSendCode();
    challengeId.value = resp.challenge_id;
  } catch (e: any) {
    codeError.value = e?.response?.data?.detail || "Не удалось переотправить код";
  }
}
"@
Apply-Patch $wizPath $old6 $new6 "[6/12] wizard: resendTestCode regenerates challenge"

# ───────────────────────────────────────────────────────────────────────
# [7/12] wizard: verifyTestCode -> verifyAndEnable
# ───────────────────────────────────────────────────────────────────────
$old7 = @"
async function verifyTestCode() {
  const code = codeDigits.value.join("");
  if (code.length !== 6) {
    codeError.value = "Введите 6 цифр кода";
    return;
  }
  busy.value = true;
  codeError.value = null;
  try {
    // Enable MFA — verifies the code as part of activation
    const resp = await mfaApi.enable("telegram");
    recoveryCodes.value = resp.recovery_codes || [];
    // Refresh /auth/me so isOwner / mfa_enabled / etc are fresh
    try {
      const me = await authApi.me();
      auth.setUser(me);
    } catch {}
    step.value = 4;
  } catch (e: any) {
    codeError.value = e?.response?.data?.detail || "Неверный код или ошибка активации";
  } finally {
    busy.value = false;
  }
}
"@
$new7 = @"
async function verifyTestCode() {
  const code = codeDigits.value.join("");
  if (code.length !== 6) {
    codeError.value = "Введите 6 цифр кода";
    return;
  }
  if (!challengeId.value) {
    codeError.value = "Сессия истекла. Нажмите «Отправить заново».";
    return;
  }
  busy.value = true;
  codeError.value = null;
  try {
    // Verify the code AND enable MFA atomically (Pack 13.3.2)
    const resp = await mfaApi.onboardingVerifyAndEnable(challengeId.value, code);
    recoveryCodes.value = resp.recovery_codes || [];
    try {
      const me = await authApi.me();
      auth.setUser(me);
    } catch {}
    step.value = 4;
  } catch (e: any) {
    codeError.value = e?.response?.data?.detail || "Неверный код";
  } finally {
    busy.value = false;
  }
}
"@
Apply-Patch $wizPath $old7 $new7 "[7/12] wizard: verifyTestCode -> verifyAndEnable"

# ───────────────────────────────────────────────────────────────────────
# [8/12] wizard: pane centering (handles both p133b1 and pre-p133b1 state)
# ───────────────────────────────────────────────────────────────────────
$panePreP1 = @'
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
$panePostP1 = @'
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
$paneNew = @'
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
Apply-Patch-EitherOf $wizPath $panePostP1 $panePreP1 $paneNew "[8/12] wizard CSS: .mfa-ob-pane centered (no flex:1)"

# ───────────────────────────────────────────────────────────────────────
# [9/12] wizard: root keep align-items center (drop justify-content)
# ───────────────────────────────────────────────────────────────────────
$rootPreP1 = @'
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
$rootPostP1 = @'
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
$rootNew = @'
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
Apply-Patch-EitherOf $wizPath $rootPostP1 $rootPreP1 $rootNew "[9/12] wizard CSS: .mfa-ob-root align-items center"

# ───────────────────────────────────────────────────────────────────────
# [10/12] wizard: step-3 phone — code placeholder (idempotent with p133b1)
# ───────────────────────────────────────────────────────────────────────
$phonePre = @"
                <div class="mfa-ob-phone-msg mfa-ob-phone-msg-code">
                  <div class="mfa-ob-pc-label" style="margin-bottom:5px">Тестовый код</div>
                  <div class="mfa-ob-phone-code">372 941</div>
                  <div class="mfa-ob-phone-code-hint">Введите в браузер. Истекает через 5 минут.</div>
                  <div class="mfa-ob-phone-time">9:41</div>
                </div>
"@
$phoneNew = @"
                <div class="mfa-ob-phone-msg mfa-ob-phone-msg-code">
                  <div class="mfa-ob-pc-label" style="margin-bottom:5px">Тестовый код</div>
                  <div class="mfa-ob-phone-code mfa-ob-phone-code-blur">••• •••</div>
                  <div class="mfa-ob-phone-code-hint">Откройте чат с @UzAssets_bot — код пришёл туда.</div>
                  <div class="mfa-ob-phone-time">9:41</div>
                </div>
"@
# This patch is idempotent: if already applied by p133b1, just skip
Write-Host "[*] [10/12] wizard: step-3 phone code placeholder" -ForegroundColor Yellow
$wsrc = Read-File $wizPath
$wsrcN = $wsrc.Replace("`r`n", "`n")
if ($wsrcN.Contains($phoneNew.Replace("`r`n", "`n"))) {
    Write-Host "    SKIP: already applied" -ForegroundColor DarkGray
} else {
    Apply-Patch $wizPath $phonePre $phoneNew "    (applying)"
}

# ───────────────────────────────────────────────────────────────────────
# [11/12] wizard CSS: .mfa-ob-phone-code-blur (idempotent)
# ───────────────────────────────────────────────────────────────────────
$blurPre = @'
.mfa-ob-phone-code {
  font-family: ui-monospace, "SF Mono", Menlo, monospace;
  font-size: 24px; font-weight: 500;
  color: white; letter-spacing: 0.12em;
  text-align: center; padding: 6px 0;
  animation: mfa-code-reveal .6s ease;
}
'@
$blurNew = @'
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
Write-Host "[*] [11/12] wizard CSS: .mfa-ob-phone-code-blur" -ForegroundColor Yellow
$wsrc = Read-File $wizPath
if ($wsrc.Contains(".mfa-ob-phone-code-blur")) {
    Write-Host "    SKIP: already applied" -ForegroundColor DarkGray
} else {
    Apply-Patch $wizPath $blurPre $blurNew "    (applying)"
}

# ───────────────────────────────────────────────────────────────────────
# [12/12] real logo PNG + new UzaLogo.vue
# ───────────────────────────────────────────────────────────────────────
$logoB64 = @"
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
2b5K6X6rb/dc/N+5rvzZcDZvkrpfqtv91z837mu/Nlze/qz8r+f0p+FT8j7fc+fL5vpkfb7nz5fN
sdekOB6j1bfIA9LQAAAAAAAA5ml6ln6Xfpv4GVfx7kTzj3Ov2x2OGPM1i3WFzHlvjtvSdpS1s/ir
V1qMXX7XyRkW+z9MJW07Nxc/GpyMW9Rdt1Rziqmeap7f7R3Vqe28um5i3aq7EzHutirxJj/VH59B
Fo3o3Tg3a7LhmMep8Y91nDn2tBs/c2BuTT4yMSuIriP6y3PjUy3/AHIm1ZrO0uk4M+PUUjJjneJf
oB5XwAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAGJ8VRfpS/HPrXotfw6V6
J8VRfpS/HPrXotfw6U3wH7ifhZzdEXgNzY4zb8en50e1hm349Pzo9ql/LJD0g2b5K6X6rb/dc/N+
5rvzZcDZvkrpfqtv91z837mu/Nlze/qz8r+f0p+FT8j7fc+fL5vpkfb7nz5fNslfLDgeo9S3yAKr
QAABzADmcwAAAAAAbLbus52hapaz8C7NFymfso+9uR5pWK2XuPE3LpVOXjz1a48F2330VeZWN2HY
m5MnbeuUZVuaqseuYpyLfdNPn9MMLV6aMld46to7OccvocsY7z+Sf/FmY585h+uUcpcXTsq1nYdv
KsVRXbuUxNNUd8OVzQcxtO0uu0vF6xavSWQFHsAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAABifFUX6Uvxz616LX8OleifFUX6Uvxz616LX8OlN8B+4/hZzdEXgNzY4zb8en50e1h
m349Pzo9ql/LJD0g2b5K6X6rb/dc/N+5rvzZcDZvkrpfqtv91z837mu/Nlze/qz8r+f0p+FT8j7f
c+fL5vpkfb7nz5fNslfLDgeo9S3yAKrQknSuFOXqGm4+bTq1FuL1umvl7l2RPhRtV3LR7O8O2NN9
Xo9kMHWZr4qxyts7K8M0+uyXjNG+0Iw+BzN/HNv6Bj4HM38c2/oP/lNIjvrs3u3j+leHfsQt8Dmb
+Obf0B8Dmb+Obf0Caf8AvtP++0+uy+5/SnDv2ITucHdQppmbWrWJn5bc0tBq/Djc2BE10YtGXR/w
avsli+T8VRE93N6rr8kdWPn7IaC8fliYlUq/ZvWLtVq/art3aZmJprjqzH6JfNZjdW0NI3Dj1U5e
NRF3l9hdpjlXTPpQJvLbGftrPm1lR17NUz7nf7qoSOn1dcvh0lo3GOzefh/548a+7RB6RmNcDv8A
wZAEwcC9yVXLd3QMqvw2469j5vfCXJ86qm29Sr0jW8XUbdXKbN2Jq+WnsqWjxMijJxrd+1Vzorpi
qJ+RB67FyX5o/V1jsjxKdTppxXnxr/8AHJAYLcAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAGJ8VRfpS/HPrXotfw6V6J8VRfpS/HPrXotfw6U3wH7j+FnN0ReA3NjjNvx6PnU+1
hm349HzqfapfyyQ9INneSumeq2/Y5+d9zXfRLX7P8ldL9Vt+yGwzvua76Jc3v6s/K/n9KfhU/I+3
3Pny+b6ZH2+58+XzbJXyw4HqPUt8gCq0Vdy0ezfJfTvV6PYq5V3LR7N8l9O9Xo9iM4l5Yb72F9XJ
8NxM8omZ7la91dJTN0Xc+q6PTtq1ejBzL2NFyb3LrdSuaef+SylXhiXnVxR+MvdH+L5X8ap64NpM
WovaMkb7Q6NltNY8E4fXUZ/5K2fp3JwOlRE3opz9q1U2++uzf5qyDYZ4NpP2rPeW918eHnGPZe8q
qMbEz6cXPmPubInqVJIeY9uuq3cprormi5RMTTXHgmJWz6L/ABZv6/RTtHcN2a8+xRzxb9c+G9TH
n+VCcS4N3FZyYunsu0y7+ErBzHytPufRcTXdKu4WXapqpqjnTVPdV3S3MscoiOSBraazvCubDTNS
aXjeJVS13TMjR9Wv6dkxzrtV9XnP31PncFLfH3RqaZxtbs0xExPuV2f3USNj0+XvMcS4jxnQ/Q6u
2L9P0AF5FCxHB/UYz9l4vWnrVY/OzM+eaVd0w9HzL54uo4k/eXKaoYWvrzY922dkNTOPXcnulwBB
OuAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAMT4qi/Sl+OfWvRa/h0r0T4qi
/Sl+OfWvRa/h0pvgP3H8LOboi8BubHGbfj0fOp9rDNHj0fOp9ql/LJD0f2d5K6X6tR7GxzvuW56J
9jXbN8ldL9Vo/dbHO+5bnon2Ob39Wflfzelb4VOyPt9z58vm+mR9vufPl82yV8sOB6j1bfIAqtFX
ctHszyX071ej2KuVdy0ezPJfTvV6PYjOJeWG+dhvWyfDcVeLPoedXE/4y90f4vl/xq3orV4s+h51
cT/jL3R/i+X/ABq2V2e9W3w6Nm6OugNtY42m0tayNu7k07W8WqaLuHkUXfB30xPOY/TDVvzV2Vei
XjLWLUmJVidpemWn5FOVg4+TRMcr1umuP0xzclo9hT1tm6RM9s4lr92G7hzbJWK3mIZsTu6bxfxo
ydkZszHiRFf6ldVleKHL+g+px/wZVqpTHDp/JLlnbasRq6zHsAJBpQk3o/18taz7X/Bpn/NGSSOA
XlPmerfzsbVx/alO9nJ24hj2906gNedrAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAYnxVF+lL8c+tei1/DpXonxVF+lL8c+tei1/DpTfAfuP4Wc3RF4Dc2OM2/Hp+dHtYZt+PT8
6PapfyyQ9INm+Sul+q2/3XPzfua782XA2b5K6X6rb/dc/N+5rvzZc3v6s/K/n9KfhU/I+33Pny+b
6ZH2+58+XzbJXyw4HqPUt8gCq0Vdy0ezPJfTvV6PYq5V3LR7M8l9O9Xo9iM4l5Yb52G9bJ8NxX4s
+iXnVxQqp+EvdHhj/wC75f8AGqeisxzdVy+HuycvLvZOTtjSr1+/XNy5XVjxNVVUzzmZWuG6+ujv
Npjfd0jJXm8Hnj1qPw4/Wdaj8OP1vQz4NNh/klo/7LSfBpsP8ktH/ZaUz/UWP9srfcz7vPPrUfhx
+tiaqZoq8NPY9Dfg02H+SWj/ALLSfBpsP8k9H/ZoUt2hxzG3LJ3M+7YbA8jNH9Tt+xvnwxse1jWK
LGPbpt2rdMU0URHKKafND7w1a9ua8291+I2h1bih5Ean+YlWulZTih5D6n+Zn2q10pjh3py5f23+
6r8ACRaQJH4AeU+b6t/MjhI/ADynzfVv5mPqvSlN9nP8jj+U7ANddtAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAYnxVF+lL8c+tei1/DpXonxVF+lL8c+tei1/DpTfAfuP4Wc3R
F4Dc2OM2/Hp+dHtYZt+PT86PapfyyQ9INneSul+q2/3YbDN+5bnzZ9jX7O8ldL9Vt/uw2Gd9y3Pm
z7HN7+rPyv5vSt8KnZH2+58+XzfTI+33Pny+bY6eWHA8/qW+QB6WiruWj2Z5L6d6vR7FXKu5aPZn
kxp/q9HsRnEvLDfOw3rZPhuh+ZnlHhdSzuI+x8LOv4eXubTbORYuVW7tqu9ETRVTPKYlE0pa87Vj
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
Xp/uU+FUJ44Nw3Hkp3uSN/ZXLeYnaHbM/iVvzNv+7ZW6tSmr85y9j76VxV4g6ZXFWNurUZ/4ddfW
plyuCPDyOIu572mV6jODYx7EXb1dMc65jnyiITRq3RZ0+qxz03c+XTd6vLletxMVJLUajQ4L93ki
P+Lda3nxhwuDfSB3Bqu59O27uHBx8mrMu+505NrwTH6O9aCFNdr8Jd3bH4sbcv6hhe+cKM6j/asa
OdEelcmP82t8Vrgi8Tg6Sv45t+r9AIxcAAAAAAAAAAAAAAAAAAAAAAO+FZ+m/YmrB29kd1N25Ssw
hLphaFc1ThjGo2aedzTcim9PzeyWdwy8U1VZl4vHgpm3nD+/axN76LkXq+ratZ1uZloyiqaK6aqf
saqJiqPklvuSvNSYhiRO0vTSzVFdqmqPDExExL6Ib6P/ABY0ndW3cXStSzLePrWLbi3XRXPL3aI8
EVUphpqpmnrRPb5p5uc6jT3w5JraGZE7w/cqjdNfKor3ppOH/vLWJVc/zWY3lu7QdpaTd1DWs+1Y
t0RMxT1o69c+aI75UR4rbvyN8b1zNdvUVW7VdXUx6PwLcJjgemvObvNvCFvLaIjZ1ZIXRwpqr4y6
BEc/ttco9TX0PtDr1HiZXqlVE1WdOx5nrz+FU2TiN4pprTPss0j8y5sHJl871yizbqu3JimmmJmZ
nuhz6PFmOu8R92YGy9q5Wu59cRTapmLdHfXXPZEKBbu17UdzbizNb1GqasjKrmufD4tP4MJD6SvE
Wvee7Z0/Av8A/wBG02qaLUd1y531om9DdODaH6fH3lvNLFyX3nZm3RXduU2rdE11VzEUxEc5me6I
Xd6N/DmjZG06cvPtU/VfPiK8ie+iJ7KENdFHhtOt6zG7tWsT9T8SqPetNU+C5c75W/jsR3G9fzT3
NP5e8VP1lkHA17UbGk6Pl6nk1dWxi2qrlc/JENciN52hfVq6aG8IrydP2biXKeVH+15no7KVavD9
9297d771+/ufdmpa5k1c6su9NUfJR3NI6Fw/TfT4K0Yd7bykDo/7Xp3TxL0/HyIp96YtfvnIjzxQ
vlTkY/LwX7f/AFQ808TLysOuqvFybtiqY5TNuuYlyPqzrH41zvp6mDxHhd9Zki3NtEPVMnLC3HS3
21Z1zYVOtY/udWXpNfukeGPFntU5+98DmXdW1S7bqt3dSzK7dUcppm9MxLhszh+ktpcXJa27ze3N
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
duu3u/Doqrw9Qp6mRVH+7u09koEeku49G0/cGj5Gk6pj038TIpmm5RKonFbgBuTb2Xdzdt2atY0v
xopp+3Wv0d7J4RxSk44xZZ2mOimTH47w0nBHi7qPDzJqxL9mrM0W/XE3LP31ufwqVndG45cN9Rxa
b87gtYszHOaL9E0VQozm4mXg1zTm4uRjVRMxMXrc2/a4810T210frhmarhem1Vuffaf9PNbzWNl5
tZ498NtMtzP1bnLnupxrU1Ir3n0nc3JqnG2no0YtM1cvfOXPWn0xTCu2Fh5eZXFOFh38qZ5REWbN
VfsSNsTgjvzceTZu16VXpuHziZyMv7GqY590MX8N0OmjmvO/8vUXvZdbamTezNtadl5NcVXruNRX
XMeDwzCLul7pl3P4SXb9m3FdeJl2rtXzecxKVtv4VWm6JhYFVcXKsezTb60eDrco5G4NLxdb0fL0
rNoi5i5VqbdynzxLWsWWMWoi8dIlemPDZ5rtts/cWp7U3Di67pF2KMvGnnTFfi3Intpl2zixwq3H
sjV71MYOTmaXVXM4+XZomuOr3RVEI9qmKZmiaopmO2Jnsb7TLi1GPwneJYm0xKxX10+r+8up/RjF
jI6njzfmaeb48JeK+8t78aNFx9UzacfBn3SYxMePsJ5Ud6v2PZu5NcUY1q5fuT97aomuf8k29GbY
W67XEXTNx5Oi5GLpmPFyZvX46vOZpReq0mjwYbTWI32XK2tMxCd+kRvPWNjbUwta0aLVVz37TbuU
XOyumYnwOs7K6Sm09Us0WtfsZGj5U+CZqp61uZ+SYb/pO7T1vd2wLWDoWLTk5VnJpvdTzxEdymut
7b3DouRVj6pouo4lyjti5Zq5f9UeBHcO0em1ODa8/mer2tErobh4wcLbuj5FrM1zFzLFyiaa7NNE
1zVHoUl1y5hXtYzLum2ps4dd6ubFE91HPwOFzoirlzo9j6Y9q9kXIt49u5fqmY5U2qJrnn6ITei0
WLR7zW3VbtabbPnNM1RMURzq5Tyjzy9FOGGPexOHe38e/P8AWW9OsxVz+ZCsXAXgjq2r6xja9unC
uYOmY9cXLWPdjlXfq+WFvrVFNuimiiIpppjlER3QhOO6ymW0Y6Tvsu4qzHjL6gNfXgAAAAAAAAAA
AAAAAAAAAAAAAAAHAz9I0vPjlm6fiZH52zFXtai7sLZtyua69t6ZNU9v+z0/6OzD3XLevSVJhpcP
bG3cKYnE0TTrMx2dTHphuKaKaI5U0xEfI/R+h5m9rdZNoAFFXxyLFnIsTayLVF23PbTXTzhxZ0XS
vxbifQ0th6DmrFpjpJs4H1G0r8WYn0VJ9R9L/FuL9FS54r3lvccD6j6X+LcX6Kk+o+l/i3F+ipc8
O8t7mzhY+m4Fiqqqxh49qqY5TNFuI8D8zo+lz26bifQUueKc9uu5s4H1I0r8W4n0VL74uNjY1HUx
7FuzTPdRTEOQE2tPWQAUBiYiY5T4YZAa+rSdMrmZq07FmZ7Zm1DP1H0r8WYn0NLnj1z29zZxcTDx
cSmYxbFqzFU85i3RFPNyaqYqjlMMjzvMzvI0+dtzQc6Zqy9GwL8z21XMemrm4ePsbaGPX17G29Lo
q8/van/R2TwD3GbJHSVNocXDw8bDtRbxrFqzbjspt0RTDlA8TMz4yqOPlYuPlW+pkWbd2mfva6eb
kBEzE+A69lbL2nleHI27plc9vP3tTH/o++n7W25gVU1Yeh6dYqp7JoxqYqj9LdD3OW8xtupsxERH
YyDwqAA1mo6Jo2o+HP0rCyZ892zTV7WsjYmzvdfdv6NaX7p28/e1PN2b9A9Vy5I6WNmtwNE0jA+4
9Mw8b5bVmmj2NkDzNpnxmQAB8r1q3etzbu26K6J7YqjnEtHlbM2plV9fI29plyrnz5zjU8/Y7DHM
l6re9PLOym0S1GBtzQMCuKsLRsDGqjsm1Yppn2NtFMRHgiGRSbWt5pVHGzMPFy7c28nHtXqPNcoi
qHJFN5joOu5WyNo5M9bI23pdU+rUx/6OVp+2tv6fVFeDoun49UdlVvHpifY3A9zlvPhupsxDIPCo
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAD/9k=
"@
Write-Base64-File $logoPng $logoB64 "[12a/12] frontend/public/uzassets-logo.png" -Overwrite

$uzaLogoNew = @'
<script setup lang="ts">
/**
 * UzaLogo — UzAssets brand mark (image-based, served from /uzassets-logo.png).
 * Pack 13.3.2: replaced the hand-drawn SVG approximation with the real logo.
 */
withDefaults(defineProps<{
  size?: number | string;
}>(), {
  size: 32,
});
</script>

<template>
  <img
    src="/uzassets-logo.png"
    :width="size"
    :height="size"
    alt="UzAssets"
    class="uza-logo"
  />
</template>

<style scoped>
.uza-logo {
  display: inline-block;
  object-fit: contain;
  user-select: none;
}
</style>
'@
Write-Host "[*] [12b/12] frontend/src/components/UzaLogo.vue (img wrapper)" -ForegroundColor Yellow
if (Test-Path -LiteralPath $logoVue) { Backup-File $logoVue }
Write-File $logoVue $uzaLogoNew
Write-Host "    OK overwritten" -ForegroundColor Green

# ───────────────────────────────────────────────────────────────────────
# Rebuild + restart frontend
# ───────────────────────────────────────────────────────────────────────
function Find-Container($pattern) {
    try {
        $all = (docker ps --format "{{.Names}}" 2>$null) -split "`n" | Where-Object { $_ -and $_.Trim() }
        foreach ($name in $all) { if ($name -match $pattern) { return $name } }
    } catch {}
    return $null
}
$fe = Find-Container "frontend|^uza-frontend"
if (-not $fe) {
    Write-Host ""
    Write-Host "[!] Frontend container not running. Rebuild manually:" -ForegroundColor Yellow
    Write-Host "    docker exec <frontend> npx vite build" -ForegroundColor White
    Write-Host "    docker restart <frontend>" -ForegroundColor White
} else {
    Write-Host ""
    Write-Host "[=] Rebuilding frontend production bundle" -ForegroundColor Cyan
    docker exec -e NODE_OPTIONS=--max-old-space-size=4096 -e VITE_API_BASE_URL= $fe npx vite build
    if ($LASTEXITCODE -ne 0) { throw "vite build failed" }
    Write-Host "    build OK" -ForegroundColor Green
    Write-Host ""
    Write-Host "[=] Restarting frontend container" -ForegroundColor Cyan
    docker restart $fe | Out-Null
    Write-Host "    restarted" -ForegroundColor Green
}

Write-Host ""
Write-Host "===================================================================" -ForegroundColor Green
Write-Host " p133b2 COMPLETE — all three issues fixed" -ForegroundColor Green
Write-Host "===================================================================" -ForegroundColor Green
Write-Host ""
Write-Host "IMPORTANT: backend changes require backend restart for new endpoints:" -ForegroundColor Yellow
Write-Host "    cd backend; docker compose restart backend; cd .." -ForegroundColor White
Write-Host ""
Write-Host "Verify:" -ForegroundColor Cyan
Write-Host "  1. Hard refresh (Ctrl+Shift+R)" -ForegroundColor White
Write-Host "  2. Onboarding pane should be centered on screen" -ForegroundColor White
Write-Host "  3. Real UzAssets logo (UA blue+teal monogram) appears everywhere" -ForegroundColor White
Write-Host "  4. Step 3: actual 6-digit code arrives in Telegram chat" -ForegroundColor White
Write-Host "  5. Type the code -> step 4 with 10 recovery codes" -ForegroundColor White
