<script setup lang="ts">
/**
 * MfaOnboarding — first-login wizard for enabling 2FA via Telegram.
 *
 * Concept C: split-pane layout with descriptive left column and animated
 * phone mockup on the right showing "what you'll see in Telegram".
 *
 * Steps:
 *   1. Welcome      — pitch + Set up / Skip 7 days
 *   2. Link Telegram— QR code + status polling for telegram_linked
 *   3. Test Code    — 6-digit input, verifies TG delivery
 *   4. Recovery     — 10 codes, download .txt + copy all, gate via checkbox
 *
 * Backend endpoints used:
 *   GET  /mfa/onboarding/status   — only on mount, to confirm wizard needed
 *   POST /mfa/onboarding/skip     — 7-day defer
 *   POST /mfa/onboarding/complete — clear skip marker after success
 *   POST /mfa/link-telegram       — generates deep_link + token
 *   GET  /mfa/status              — polled every 2s on step 2 for telegram_linked
 *   POST /mfa/test-notification   — sends the 6-digit code on step 3 entry
 *   POST /mfa/enable              — finalizes 2FA, returns recovery_codes
 */
import { ref, computed, onMounted, onBeforeUnmount, nextTick, watch } from "vue";
import { useRouter } from "vue-router";
import QRCode from "qrcode";
import UzaLogo from "@/components/UzaLogo.vue";
import { mfaApi } from "@/api/mfa";
import { authApi } from "@/api/auth";
import { useAuthStore } from "@/stores/auth";
import { useFormatters } from "@/composables/useFormatters";

const fmt = useFormatters();

const router = useRouter();
const auth = useAuthStore();

const step = ref<1 | 2 | 3 | 4>(1);
const error = ref<string | null>(null);
const busy = ref(false);
const challengeId = ref<string>("");  // Pack 13.3.2: id of the onboarding code challenge

// ─── Step 2: link Telegram ──────────────────────────────────────────
const qrDataUrl = ref<string>("");
const deepLink = ref<string>("");
const linkExpiresAt = ref<Date | null>(null);
const remainingSec = ref(0);
let pollTimer: number | null = null;
let tickTimer: number | null = null;

// ─── Step 3: test code ──────────────────────────────────────────────
const codeDigits = ref<string[]>(["", "", "", "", "", ""]);
const codeInputs = ref<(HTMLInputElement | null)[]>([null, null, null, null, null, null]);
const codeError = ref<string | null>(null);

// ─── Step 4: recovery codes ─────────────────────────────────────────
const recoveryCodes = ref<string[]>([]);
const recoveryAcknowledged = ref(false);
const copiedToast = ref(false);

// ─── Derived ────────────────────────────────────────────────────────
const firstName = computed(() => {
  const full = auth.user?.full_name || "";
  if (full) return full.split(" ")[0];
  const email = auth.user?.email || "";
  return email.split("@")[0] || "коллега";
});

const userFullName = computed(() => auth.user?.full_name || auth.user?.email || "");
const userEmail = computed(() => auth.user?.email || "");
const userRoleLabel = computed(() => {
  if (auth.user?.is_owner) return "Администратор платформы";
  const roles = auth.user?.roles || [];
  const map: Record<string, string> = {
    admin: "Администратор",
    financier: "Финансист",
    department_head: "Руководитель отдела",
    consultant: "Консультант",
    auditor: "Аудитор",
    viewer: "Наблюдатель",
  };
  for (const r of roles) {
    const lower = r.toLowerCase();
    if (map[lower]) return map[lower];
  }
  return roles[0] || "Пользователь";
});

const remainingMmSs = computed(() => {
  const m = Math.floor(remainingSec.value / 60);
  const s = remainingSec.value % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
});

// ─── Step 2 lifecycle ───────────────────────────────────────────────
async function startSetup() {
  step.value = 2;
  await nextTick();
  await initLinkStep();
}

async function initLinkStep() {
  busy.value = true;
  error.value = null;
  qrDataUrl.value = "";
  try {
    const resp = await mfaApi.linkTelegram();
    deepLink.value = resp.deep_link;
    linkExpiresAt.value = new Date(resp.expires_at);
    qrDataUrl.value = await QRCode.toDataURL(resp.deep_link, {
      margin: 1,
      width: 256,
      color: { dark: "#1E2A4A", light: "#FFFFFF" },
      errorCorrectionLevel: "M",
    });
    startTicker();
    startPolling();
  } catch (e: any) {
    error.value = e?.response?.data?.detail || "Не удалось получить QR-код";
  } finally {
    busy.value = false;
  }
}

function startTicker() {
  stopTicker();
  tickTimer = window.setInterval(() => {
    if (!linkExpiresAt.value) return;
    const ms = linkExpiresAt.value.getTime() - Date.now();
    remainingSec.value = Math.max(0, Math.floor(ms / 1000));
    if (remainingSec.value === 0) {
      stopTicker();
      stopPolling();
      // Auto-refresh QR
      void initLinkStep();
    }
  }, 1000);
}

function stopTicker() {
  if (tickTimer !== null) {
    clearInterval(tickTimer);
    tickTimer = null;
  }
}

function startPolling() {
  stopPolling();
  pollTimer = window.setInterval(async () => {
    try {
      const st = await mfaApi.status();
      if (st.telegram_linked) {
        stopPolling();
        stopTicker();
        // Move to step 3, kick off test-code delivery
        await proceedToTestCode();
      }
    } catch {
      // Network blip — keep polling
    }
  }, 2000);
}

function stopPolling() {
  if (pollTimer !== null) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

async function openBotDirect() {
  if (deepLink.value) window.open(deepLink.value, "_blank");
}

// ─── Step 3 ────────────────────────────────────────────────────────
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

function onCodeInput(idx: number, ev: Event) {
  const input = ev.target as HTMLInputElement;
  let v = (input.value || "").replace(/\D/g, "");
  if (v.length > 1) {
    // User pasted — distribute digits across cells
    const digits = v.slice(0, 6).split("");
    for (let i = 0; i < digits.length && idx + i < 6; i++) {
      codeDigits.value[idx + i] = digits[i];
    }
    const last = Math.min(idx + digits.length, 5);
    codeInputs.value[last]?.focus();
    return;
  }
  codeDigits.value[idx] = v;
  if (v && idx < 5) {
    codeInputs.value[idx + 1]?.focus();
  }
}

function onCodeKeydown(idx: number, ev: KeyboardEvent) {
  if (ev.key === "Backspace" && !codeDigits.value[idx] && idx > 0) {
    codeInputs.value[idx - 1]?.focus();
  } else if (ev.key === "ArrowLeft" && idx > 0) {
    codeInputs.value[idx - 1]?.focus();
  } else if (ev.key === "ArrowRight" && idx < 5) {
    codeInputs.value[idx + 1]?.focus();
  } else if (ev.key === "Enter") {
    void verifyTestCode();
  }
}

async function resendTestCode() {
  codeError.value = null;
  try {
    const resp = await mfaApi.onboardingSendCode();
    challengeId.value = resp.challenge_id;
  } catch (e: any) {
    codeError.value = e?.response?.data?.detail || "Не удалось переотправить код";
  }
}

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

// ─── Step 4: recovery codes ─────────────────────────────────────────
function downloadRecoveryTxt() {
  const today = new Date().toISOString().slice(0, 10);
  const lines = [
    "UzAssets — резервные коды двухфакторной аутентификации",
    "",
    `Аккаунт: ${userFullName.value}`,
    `Email:   ${userEmail.value}`,
    `Дата:    ${fmt.fmtDateTime(new Date())}`,
    "",
    "Каждый код используется один раз. Храните в надёжном месте.",
    "",
    ...recoveryCodes.value.map((c, i) => `${(i + 1).toString().padStart(2, "0")}.  ${c}`),
    "",
    "Никогда не отправляйте эти коды в чаты, email или Telegram.",
  ];
  const blob = new Blob([lines.join("\r\n")], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `uzassets-recovery-codes-${today}.txt`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

async function copyAllCodes() {
  const txt = recoveryCodes.value.join("\n");
  try {
    await navigator.clipboard.writeText(txt);
    copiedToast.value = true;
    setTimeout(() => (copiedToast.value = false), 1800);
  } catch {
    // Fallback: select + copy via execCommand
  }
}

async function completeOnboarding() {
  if (!recoveryAcknowledged.value) return;
  try {
    await mfaApi.onboardingComplete();
    // Refresh user — mfa_enabled/mfa_onboarding_skipped_until теперь актуальны
    try { auth.setUser(await (await import("@/api/auth")).authApi.me()); } catch {}
  } catch {}
  router.push({ name: "home" });
}

async function skipOnboarding() {
  busy.value = true;
  try {
    await mfaApi.onboardingSkip();
  } catch {}
  router.push({ name: "dashboard" });   // skip -- не welcome, сразу к работе
}

// ─── Lifecycle ──────────────────────────────────────────────────────
onMounted(async () => {
  // Если ещё не сменил пароль — выгнать на change-password ДО показа MFA.
  // Pack 151: password change должен быть первым в onboarding.
  if (auth.user?.must_change_password === true) {
    router.replace({ name: "change-password" });
    return;
  }
  // Defensive: if user landed here but onboarding not needed, bounce out
  try {
    const st = await mfaApi.onboardingStatus();
    if (!st.needed) {
      router.replace({ name: "dashboard" });
    }
  } catch {
    // If endpoint unavailable, stay — wizard works fine without status
  }
});

onBeforeUnmount(() => {
  stopPolling();
  stopTicker();
});
</script>

<template>
  <div class="mfa-ob-root">
    <!-- Top brand strip -->
    <div class="mfa-ob-topbar">
      <div class="mfa-ob-brand">
        <UzaLogo :size="22" />
        <span>UzAssets</span>
      </div>
      <div class="mfa-ob-step-pills">
        <div class="mfa-ob-pill" :class="step >= 1 ? 'is-active' : ''"></div>
        <div class="mfa-ob-pill" :class="step >= 2 ? 'is-active' : ''"></div>
        <div class="mfa-ob-pill" :class="step >= 3 ? 'is-active' : ''"></div>
        <div class="mfa-ob-pill" :class="step >= 4 ? 'is-active' : ''"></div>
        <span class="mfa-ob-step-counter">{{ step }} / 4</span>
      </div>
      <button v-if="step < 4" class="mfa-ob-skip-link" :disabled="busy" @click="skipOnboarding">
        Напомнить через 7 дней
      </button>
      <span v-else></span>
    </div>

    <!-- Step body — split pane -->
    <transition name="mfa-ob-fade" mode="out-in">
      <!-- ════════ STEP 1: WELCOME ════════ -->
      <div v-if="step === 1" key="s1" class="mfa-ob-pane">
        <div class="mfa-ob-left">
          <div class="mfa-ob-badge">
            <UzaLogo :size="14" />
            <span>ВКЛЮЧИТЕ 2FA · ШАГ 1 / 4</span>
          </div>
          <h1 class="mfa-ob-h1">Здравствуйте,<br/>{{ firstName }}!</h1>
          <p class="mfa-ob-lead">
            Рекомендуем добавить второй фактор входа через Telegram.
            Это займёт две минуты и серьёзно повысит безопасность вашего аккаунта.
          </p>

          <div class="mfa-ob-bullets">
            <div class="mfa-ob-bullet">
              <div class="mfa-ob-bullet-icon"><svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg></div>
              <div><strong>Мгновенно.</strong> Коды приходят в Telegram за секунду — не ждёте SMS.</div>
            </div>
            <div class="mfa-ob-bullet">
              <div class="mfa-ob-bullet-icon"><svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg></div>
              <div><strong>Безопасно.</strong> Даже если пароль утечёт, без вашего телефона войти невозможно.</div>
            </div>
            <div class="mfa-ob-bullet">
              <div class="mfa-ob-bullet-icon"><svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg></div>
              <div><strong>Бесплатно.</strong> Никаких SMS-операторов и платных сервисов.</div>
            </div>
          </div>

          <div class="mfa-ob-actions">
            <button class="mfa-ob-btn-primary" :disabled="busy" @click="startSetup">
              Настроить сейчас
              <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
            </button>
          </div>
        </div>

        <!-- Right: phone (welcome state) -->
        <div class="mfa-ob-right">
          <div class="mfa-ob-phone">
            <div class="mfa-ob-phone-notch"></div>
            <div class="mfa-ob-phone-screen" style="background: linear-gradient(180deg, #17212B 0%, #1a2738 100%);">
              <div class="mfa-ob-phone-halo"></div>
              <div class="mfa-ob-phone-status">
                <span>9:41</span>
                <span class="mfa-ob-phone-status-icons">
                  <svg viewBox="0 0 24 24" width="9" height="9" fill="currentColor"><path d="M2 9h20v6H2z" opacity=".3"/><path d="M2 9h14v6H2z"/></svg>
                </span>
              </div>
              <div class="mfa-ob-phone-welcome">
                <div class="mfa-ob-phone-logo-card">
                  <UzaLogo :size="60" />
                </div>
                <div class="mfa-ob-phone-bot-name">UzAssets Bot</div>
                <div class="mfa-ob-phone-bot-handle">@UzAssets_bot</div>
                <button class="mfa-ob-phone-cta">Запустить</button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- ════════ STEP 2: LINK TELEGRAM ════════ -->
      <div v-else-if="step === 2" key="s2" class="mfa-ob-pane">
        <div class="mfa-ob-left">
          <div class="mfa-ob-badge mfa-ob-badge-purple">
            <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>
            <span>ПРИВЯЗКА · ШАГ 2 / 4</span>
          </div>
          <h1 class="mfa-ob-h1">Привяжите Telegram</h1>
          <p class="mfa-ob-lead">
            Бот <strong class="mfa-ob-mono">@UzAssets_bot</strong> станет вашим каналом получения кодов.
            Привяжите его к вашему телефону один раз.
          </p>

          <div class="mfa-ob-steps">
            <div class="mfa-ob-step-row">
              <div class="mfa-ob-step-num">1</div>
              <div>
                <div class="mfa-ob-step-title">Сканируйте QR-код</div>
                <div class="mfa-ob-step-desc">камерой телефона или в Telegram → меню → «Сканировать QR»</div>
              </div>
            </div>
            <div class="mfa-ob-step-row">
              <div class="mfa-ob-step-num">2</div>
              <div>
                <div class="mfa-ob-step-title">В боте нажмите «Это я, {{ userFullName }}»</div>
                <div class="mfa-ob-step-desc">бот покажет ваше имя и email для подтверждения</div>
              </div>
            </div>
            <div class="mfa-ob-step-row">
              <div class="mfa-ob-step-num mfa-ob-step-num-done">
                <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
              </div>
              <div>
                <div class="mfa-ob-step-title">Готово — перейдём дальше автоматически</div>
              </div>
            </div>
          </div>

          <!-- QR card -->
          <div class="mfa-ob-qr-card">
            <div class="mfa-ob-qr-img-wrap">
              <img v-if="qrDataUrl" :src="qrDataUrl" alt="QR code" class="mfa-ob-qr-img"/>
              <div v-else class="mfa-ob-qr-loading">
                <div class="mfa-ob-spinner"></div>
              </div>
            </div>
            <div class="mfa-ob-qr-info">
              <div class="mfa-ob-qr-title">QR-код для сканирования</div>
              <div class="mfa-ob-qr-status">
                <span class="mfa-ob-status-dot"></span>
                <span v-if="qrDataUrl">Ждём сканирования · истекает {{ remainingMmSs }}</span>
                <span v-else>Загрузка…</span>
              </div>
            </div>
            <button class="mfa-ob-btn-dark" :disabled="!deepLink" @click="openBotDirect">
              Открыть бота
            </button>
          </div>

          <div v-if="error" class="mfa-ob-error">{{ error }}</div>
        </div>

        <!-- Right: phone with bot chat -->
        <div class="mfa-ob-right">
          <div class="mfa-ob-phone">
            <div class="mfa-ob-phone-notch"></div>
            <div class="mfa-ob-phone-screen">
              <div class="mfa-ob-phone-status">
                <span>9:41</span>
                <span class="mfa-ob-phone-status-icons">📶</span>
              </div>
              <div class="mfa-ob-phone-chat-hdr">
                <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="#6AB3F3" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"/></svg>
                <div class="mfa-ob-phone-avatar"><UzaLogo :size="20" /></div>
                <div>
                  <div class="mfa-ob-phone-hdr-name">UzAssets Bot</div>
                  <div class="mfa-ob-phone-hdr-sub">бот</div>
                </div>
              </div>
              <div class="mfa-ob-phone-msgs">
                <div class="mfa-ob-phone-msg">
                  Здравствуйте! Подтвердите привязку этого Telegram к вашему аккаунту:
                  <div class="mfa-ob-phone-card">
                    <div class="mfa-ob-pc-label">Имя</div>
                    <div class="mfa-ob-pc-value">{{ userFullName }}</div>
                    <div class="mfa-ob-pc-label">Email</div>
                    <div class="mfa-ob-pc-value mfa-ob-mono">{{ userEmail }}</div>
                    <div class="mfa-ob-pc-label">Роль</div>
                    <div class="mfa-ob-pc-value">{{ userRoleLabel }}</div>
                  </div>
                  <div class="mfa-ob-phone-time">9:41</div>
                </div>
                <div class="mfa-ob-phone-kbd">
                  <button class="mfa-ob-phone-kbd-btn pulse">✓ Это я, {{ userFullName }}</button>
                  <button class="mfa-ob-phone-kbd-btn dim">Это не я</button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- ════════ STEP 3: TEST CODE ════════ -->
      <div v-else-if="step === 3" key="s3" class="mfa-ob-pane">
        <div class="mfa-ob-left">
          <div class="mfa-ob-badge mfa-ob-badge-green">
            <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
            <span>TELEGRAM ПРИВЯЗАН · ШАГ 3 / 4</span>
          </div>
          <h1 class="mfa-ob-h1">Проверим канал —<br/>введите код из Telegram</h1>
          <p class="mfa-ob-lead">
            Мы только что отправили тестовый 6-значный код в чат с
            <strong class="mfa-ob-mono">@UzAssets_bot</strong>. Это нужно один раз,
            чтобы убедиться что доставка работает.
          </p>

          <div class="mfa-ob-code-input">
            <input
              v-for="(d, idx) in codeDigits"
              :key="idx"
              :ref="el => codeInputs[idx] = el as HTMLInputElement"
              type="text"
              inputmode="numeric"
              maxlength="6"
              :value="d"
              @input="onCodeInput(idx, $event)"
              @keydown="onCodeKeydown(idx, $event)"
            />
          </div>

          <div class="mfa-ob-code-meta">
            <a href="#" @click.prevent="resendTestCode">Отправить заново</a>
          </div>

          <div v-if="codeError" class="mfa-ob-error">{{ codeError }}</div>

          <button
            class="mfa-ob-btn-primary"
            :disabled="busy || codeDigits.join('').length !== 6"
            @click="verifyTestCode"
          >
            Подтвердить и продолжить
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
          </button>
        </div>

        <!-- Right: phone with code message -->
        <div class="mfa-ob-right">
          <div class="mfa-ob-phone">
            <div class="mfa-ob-phone-notch"></div>
            <div class="mfa-ob-phone-screen">
              <div class="mfa-ob-phone-status">
                <span>9:42</span>
                <span class="mfa-ob-phone-status-icons">📶</span>
              </div>
              <div class="mfa-ob-phone-chat-hdr">
                <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="#6AB3F3" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"/></svg>
                <div class="mfa-ob-phone-avatar"><UzaLogo :size="20" /></div>
                <div>
                  <div class="mfa-ob-phone-hdr-name">UzAssets Bot</div>
                  <div class="mfa-ob-phone-hdr-sub mfa-ob-phone-online">● online</div>
                </div>
              </div>
              <div class="mfa-ob-phone-msgs">
                <div class="mfa-ob-phone-msg">
                  <span style="color:#4FCC9A;">✓</span> Telegram привязан к аккаунту {{ userFullName }}.
                  <div class="mfa-ob-phone-time">9:41</div>
                </div>
                <div class="mfa-ob-phone-msg mfa-ob-phone-msg-code">
                  <div class="mfa-ob-pc-label" style="margin-bottom:5px">Тестовый код</div>
                  <div class="mfa-ob-phone-code mfa-ob-phone-code-blur">••• •••</div>
                  <div class="mfa-ob-phone-code-hint">Откройте чат с @UzAssets_bot — код пришёл туда.</div>
                  <div class="mfa-ob-phone-time">9:41</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- ════════ STEP 4: RECOVERY ════════ -->
      <div v-else key="s4" class="mfa-ob-pane">
        <div class="mfa-ob-left">
          <div class="mfa-ob-badge mfa-ob-badge-amber">
            <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
            <span>ВАЖНО · ШАГ 4 / 4</span>
          </div>
          <h1 class="mfa-ob-h1">Сохраните резервные<br/>коды на случай ЧП</h1>
          <p class="mfa-ob-lead">
            Если потеряете телефон или Telegram станет недоступен, эти 10 одноразовых
            кодов помогут войти. Каждый используется один раз.
            <strong>Покажем их только сейчас.</strong>
          </p>

          <div class="mfa-ob-codes-grid">
            <div
              v-for="(c, i) in recoveryCodes"
              :key="i"
              class="mfa-ob-code-row"
            >
              <span class="mfa-ob-code-idx">{{ (i + 1).toString().padStart(2, "0") }}</span>
              <span class="mfa-ob-code-val">{{ c }}</span>
            </div>
          </div>

          <div class="mfa-ob-code-actions">
            <button class="mfa-ob-btn-dark" @click="downloadRecoveryTxt">
              <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
              Скачать .txt
            </button>
            <button class="mfa-ob-btn-light" @click="copyAllCodes">
              <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
              {{ copiedToast ? "Скопировано ✓" : "Скопировать всё" }}
            </button>
          </div>

          <div class="mfa-ob-warn">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
            <div>Распечатайте или сохраните в менеджер паролей. Никогда не отправляйте в чаты/email/Telegram — это эквивалент пароля.</div>
          </div>

          <label class="mfa-ob-ack">
            <input type="checkbox" v-model="recoveryAcknowledged"/>
            <span>Я сохранил коды в надёжном месте</span>
          </label>

          <button
            class="mfa-ob-btn-success"
            :disabled="!recoveryAcknowledged"
            @click="completeOnboarding"
          >
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
            Завершить настройку
          </button>
        </div>

        <!-- Right: phone celebration -->
        <div class="mfa-ob-right">
          <div class="mfa-ob-phone">
            <div class="mfa-ob-phone-notch"></div>
            <div class="mfa-ob-phone-screen" style="background: linear-gradient(180deg, #17212B 0%, #1a3528 100%);">
              <div v-for="i in 4" :key="i" class="mfa-ob-confetti" :class="`mfa-ob-confetti-${i}`"></div>
              <div class="mfa-ob-phone-status">
                <span>9:43</span>
                <span class="mfa-ob-phone-status-icons">📶</span>
              </div>
              <div class="mfa-ob-phone-celebrate">
                <div class="mfa-ob-celebrate-circle">
                  <svg viewBox="0 0 24 24" width="44" height="44" fill="none" stroke="white" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><polyline points="9 12 11 14 15 10"/></svg>
                </div>
                <div class="mfa-ob-celebrate-title">2FA активирована</div>
                <div class="mfa-ob-celebrate-sub">
                  Теперь при каждом входе мы будем присылать одноразовый код в этот чат.
                </div>
                <div class="mfa-ob-celebrate-footer">
                  <UzaLogo :size="14" />
                  <span>UzAssets</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </transition>
  </div>
</template>

<!-- Pack 13.3.4: global override styles — beat any conflicting scoped CSS -->
<style>
/* === Centering override (!important kills all earlier flex/grid attempts) === */
.mfa-ob-root {
  /* #app is a flex container (main.css) — without these the root
     collapses to content width and prevents proper grid centering. */
  width: 100vw !important;
  min-width: 100vw !important;
  flex: 1 1 100vw !important;
  min-height: 100vh !important;
  /* Унифицированный фон: light girih + linear gradient (как Login/ChangePassword) */
  background-color: #F4F2FF !important;
  background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 96 96' width='96' height='96'><g fill='none' stroke='%23534AB7' stroke-width='0.6' opacity='0.14'><rect x='18' y='18' width='60' height='60'/><rect x='18' y='18' width='60' height='60' transform='rotate(45 48 48)'/><circle cx='48' cy='48' r='10'/><rect x='-12' y='-12' width='24' height='24' transform='rotate(45 0 0)'/><rect x='84' y='-12' width='24' height='24' transform='rotate(45 96 0)'/><rect x='-12' y='84' width='24' height='24' transform='rotate(45 0 96)'/><rect x='84' y='84' width='24' height='24' transform='rotate(45 96 96)'/><line x1='0' y1='48' x2='18' y2='48'/><line x1='78' y1='48' x2='96' y2='48'/><line x1='48' y1='0' x2='48' y2='18'/><line x1='48' y1='78' x2='48' y2='96'/></g></svg>"), linear-gradient(145deg, #EEF0FF 0%, #F4F2FF 40%, #EBF0FF 100%) !important;
  background-repeat: repeat, no-repeat !important;
  background-attachment: fixed, fixed !important;
  padding: 24px 16px 40px !important;
  display: grid !important;
  grid-template-columns: 1fr min(960px, 100%) 1fr !important;
  grid-template-rows: auto 1fr !important;
  row-gap: 24px !important;
  column-gap: 0 !important;
  color: var(--t1, #1E2A4A) !important;
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
/* ───── Root + topbar ───── */
.mfa-ob-root {
  min-height: 100vh;
  background: linear-gradient(180deg, #F1F3F8 0%, #E8ECF3 100%);
  padding: 24px 16px 40px;
  /* Pack 13.3.3: explicit 3-column grid for unconditional centering */
  display: grid;
  grid-template-columns: 1fr min(960px, 100%) 1fr;
  grid-template-rows: auto 1fr;
  row-gap: 24px;
  color: var(--t1, #1E2A4A);
  font-weight: 400;
}
.mfa-ob-topbar {
  grid-column: 2;       /* middle column of the 3-col grid */
  grid-row: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 0 4px;
}
.mfa-ob-brand {
  display: flex; align-items: center; gap: 8px;
  font-size: 13px; font-weight: 500;
}
.mfa-ob-step-pills {
  display: flex; align-items: center; gap: 6px;
}
.mfa-ob-pill {
  width: 28px; height: 4px; border-radius: 2px;
  background: #D1D5DB;
  transition: background .3s ease;
}
.mfa-ob-pill.is-active { background: #7F77DD; }
.mfa-ob-pill:nth-child(4).is-active { background: #1D9E75; }
.mfa-ob-step-counter {
  font-size: 11px; color: #9CA3AF; margin-left: 8px; font-weight: 500;
}
.mfa-ob-skip-link {
  background: transparent; border: none; cursor: pointer;
  color: #9CA3AF; font-size: 12px; padding: 4px 10px; border-radius: 6px;
  transition: color .15s, background .15s;
}
.mfa-ob-skip-link:hover { color: #534AB7; background: rgba(127,119,221,.06); }
.mfa-ob-skip-link:disabled { opacity: .5; cursor: not-allowed; }

/* ───── Pane (split layout) ───── */
.mfa-ob-pane {
  grid-column: 2;       /* middle column of the 3-col grid */
  grid-row: 2;
  width: 100%;
  background: rgba(255, 255, 255, 0.75);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid rgba(15, 23, 60, 0.06);
  border-radius: 22px;
  padding: 40px;
  display: grid;
  grid-template-columns: 1fr 320px;
  gap: 48px;
  align-items: center;
  box-shadow: 0 32px 80px rgba(15,23,60,.12), 0 12px 32px rgba(15,23,60,.06);
  animation: mfaPaneFadeUp 0.7s cubic-bezier(0.22, 1, 0.36, 1) both;
}
@keyframes mfaPaneFadeUp {
  0%   { opacity: 0; transform: translateY(24px); }
  100% { opacity: 1; transform: translateY(0); }
}
@media (prefers-reduced-motion: reduce) {
  .mfa-ob-pane { animation-duration: 0.01s !important; }
}
.mfa-ob-left { min-width: 0; }
.mfa-ob-right { display: flex; justify-content: center; }

/* ───── Typography ───── */
.mfa-ob-h1 {
  font-size: 26px;
  font-weight: 500;
  letter-spacing: -.015em;
  line-height: 1.2;
  margin: 0 0 10px;
  color: var(--t1, #1E2A4A);
}
.mfa-ob-lead {
  font-size: 14px;
  color: #6B7280;
  line-height: 1.6;
  margin: 0 0 24px;
  max-width: 400px;
}
.mfa-ob-mono {
  font-family: ui-monospace, "SF Mono", Menlo, monospace;
  font-size: 13px;
  font-weight: 500;
}

/* ───── Badges ───── */
.mfa-ob-badge {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 4px 11px; border-radius: 11px;
  background: rgba(127,119,221,.12); color: #534AB7;
  font-size: 11px; font-weight: 500; letter-spacing: 0.04em;
  margin-bottom: 14px;
}
.mfa-ob-badge-purple { background: rgba(127,119,221,.12); color: #534AB7; }
.mfa-ob-badge-green  { background: rgba(29,158,117,.12);  color: #0F6E56; }
.mfa-ob-badge-amber  { background: rgba(239,159,39,.16);  color: #854F0B; }

/* ───── Bullets (step 1) ───── */
.mfa-ob-bullets { display: flex; flex-direction: column; gap: 12px; margin-bottom: 28px; }
.mfa-ob-bullet {
  display: flex; gap: 12px; align-items: flex-start;
  font-size: 13px; line-height: 1.5;
}
.mfa-ob-bullet strong { font-weight: 500; }
.mfa-ob-bullet-icon {
  width: 22px; height: 22px; border-radius: 6px;
  background: #E1F5EE; color: #0F6E56;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0; margin-top: 1px;
}

/* ───── Steps list (step 2) ───── */
.mfa-ob-steps { display: flex; flex-direction: column; gap: 14px; margin-bottom: 24px; }
.mfa-ob-step-row { display: flex; gap: 14px; align-items: flex-start; }
.mfa-ob-step-num {
  width: 28px; height: 28px; border-radius: 8px;
  background: #EEEDFE; color: #534AB7;
  display: flex; align-items: center; justify-content: center;
  font-weight: 500; font-size: 13px; flex-shrink: 0;
}
.mfa-ob-step-num-done { background: #E1F5EE; color: #0F6E56; }
.mfa-ob-step-title { font-size: 14px; font-weight: 500; margin-bottom: 2px; }
.mfa-ob-step-desc  { font-size: 12px; color: #6B7280; line-height: 1.5; }

/* ───── QR card ───── */
.mfa-ob-qr-card {
  display: flex; align-items: center; gap: 18px;
  padding: 14px;
  background: var(--bg2, #F9FAFB);
  border-radius: 12px;
  border: 0.5px solid #E5E7EB;
}
.mfa-ob-qr-img-wrap {
  width: 76px; height: 76px;
  background: white; border-radius: 8px;
  padding: 4px; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
}
.mfa-ob-qr-img { width: 100%; height: 100%; display: block; }
.mfa-ob-qr-loading { width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; }
.mfa-ob-spinner {
  width: 18px; height: 18px;
  border: 2px solid #E5E7EB;
  border-top-color: #7F77DD;
  border-radius: 50%;
  animation: mfa-spin .8s linear infinite;
}
@keyframes mfa-spin { to { transform: rotate(360deg); } }
.mfa-ob-qr-info { flex: 1; min-width: 0; }
.mfa-ob-qr-title { font-size: 13px; font-weight: 500; margin-bottom: 4px; }
.mfa-ob-qr-status {
  font-size: 11px; color: #9CA3AF;
  display: flex; align-items: center; gap: 6px;
}
.mfa-ob-status-dot {
  width: 6px; height: 6px; border-radius: 50%;
  background: #7F77DD;
  animation: mfa-pulse 1.6s ease-in-out infinite;
}
@keyframes mfa-pulse {
  0%,100% { opacity: .4; transform: scale(1); }
  50%     { opacity: 1;  transform: scale(1.4); }
}

/* ───── Buttons ───── */
.mfa-ob-actions { display: flex; gap: 10px; align-items: center; }
.mfa-ob-btn-primary {
  padding: 11px 22px; border-radius: 10px;
  background: linear-gradient(90deg, #14B8A6 0%, #4F46E5 100%);
  background-size: 200% 100%;
  background-position: 0% 50%;
  border: none; color: white;
  font-size: 13px; font-weight: 600; cursor: pointer;
  display: inline-flex; align-items: center; gap: 8px;
  transition: background-position .3s ease, transform .15s cubic-bezier(0.34, 1.2, 0.64, 1), box-shadow .15s ease;
  box-shadow: 0 6px 18px rgba(20, 184, 166, 0.18), 0 3px 10px rgba(79, 70, 229, 0.18);
}
.mfa-ob-btn-primary:hover:not(:disabled) {
  background-position: 100% 50%;
  transform: translateY(-1px);
  box-shadow: 0 10px 24px rgba(79, 70, 229, 0.26), 0 4px 12px rgba(20, 184, 166, 0.18);
}
.mfa-ob-btn-primary:disabled { opacity: .5; cursor: not-allowed; }
.mfa-ob-btn-success {
  padding: 11px 22px; border-radius: 10px;
  background: linear-gradient(90deg, #1D9E75 0%, #14B8A6 100%);
  background-size: 200% 100%;
  background-position: 0% 50%;
  border: none; color: white;
  font-size: 13px; font-weight: 600; cursor: pointer;
  display: inline-flex; align-items: center; gap: 8px;
  transition: background-position .3s ease, transform .15s cubic-bezier(0.34, 1.2, 0.64, 1);
}
.mfa-ob-btn-success:disabled { opacity: .45; cursor: not-allowed; }
.mfa-ob-btn-success:hover:not(:disabled) {
  background-position: 100% 50%;
  transform: translateY(-1px);
}
.mfa-ob-btn-dark {
  padding: 9px 14px; border-radius: 8px;
  background: #1E2A4A; border: none; color: white;
  font-size: 12px; font-weight: 500; cursor: pointer;
  display: inline-flex; align-items: center; gap: 8px;
  flex-shrink: 0;
}
.mfa-ob-btn-dark:disabled { opacity: .5; cursor: not-allowed; }
.mfa-ob-btn-light {
  padding: 9px 14px; border-radius: 8px;
  background: white; border: 0.5px solid #E5E7EB; color: var(--t1, #1E2A4A);
  font-size: 12px; font-weight: 500; cursor: pointer;
  display: inline-flex; align-items: center; gap: 8px;
}
.mfa-ob-btn-light:hover { background: var(--bg2, #F9FAFB); }

/* ───── Code input (step 3) ───── */
.mfa-ob-code-input { display: flex; gap: 8px; margin-bottom: 16px; }
.mfa-ob-code-input input {
  width: 48px; height: 56px;
  background: white; border: 1.5px solid #D1D5DB;
  border-radius: 10px;
  font-size: 22px; font-weight: 500;
  font-family: ui-monospace, "SF Mono", Menlo, monospace;
  text-align: center;
  color: var(--t1, #1E2A4A);
  outline: none;
  transition: border-color .15s, box-shadow .15s;
}
.mfa-ob-code-input input:focus {
  border-color: #7F77DD;
  box-shadow: 0 0 0 4px rgba(127,119,221,.12);
}
.mfa-ob-code-meta {
  display: flex; align-items: center; gap: 12px;
  font-size: 12px; color: #9CA3AF; margin-bottom: 24px;
}
.mfa-ob-code-meta a { color: #534AB7; text-decoration: none; }
.mfa-ob-code-meta a:hover { text-decoration: underline; }

/* ───── Recovery codes (step 4) ───── */
.mfa-ob-codes-grid {
  background: var(--bg2, #F9FAFB);
  border: 0.5px solid #E5E7EB;
  border-radius: 12px;
  padding: 16px;
  margin-bottom: 16px;
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px 24px;
}
.mfa-ob-code-row {
  display: flex; align-items: center; gap: 10px;
  font-family: ui-monospace, "SF Mono", Menlo, monospace;
  font-size: 13px;
  letter-spacing: 0.04em;
}
.mfa-ob-code-idx { color: #9CA3AF; font-size: 11px; width: 16px; }
.mfa-ob-code-val { color: var(--t1, #1E2A4A); font-weight: 500; }
.mfa-ob-code-actions { display: flex; gap: 10px; margin-bottom: 16px; }
.mfa-ob-code-actions button { flex: 1; justify-content: center; }
.mfa-ob-warn {
  display: flex; align-items: flex-start; gap: 10px;
  padding: 12px 14px;
  background: rgba(239,159,39,.08);
  border: 0.5px solid rgba(239,159,39,.25);
  border-radius: 8px;
  margin-bottom: 20px;
  color: var(--t1, #1E2A4A);
}
.mfa-ob-warn svg { color: #854F0B; margin-top: 1px; flex-shrink: 0; }
.mfa-ob-warn div { font-size: 12px; line-height: 1.5; }
.mfa-ob-ack {
  display: flex; align-items: flex-start; gap: 10px;
  font-size: 13px; margin-bottom: 16px; cursor: pointer;
}
.mfa-ob-ack input {
  margin-top: 3px; width: 14px; height: 14px;
  accent-color: #1D9E75;
}

/* ───── Errors ───── */
.mfa-ob-error {
  padding: 10px 12px;
  background: rgba(226,75,74,.08);
  border: 0.5px solid rgba(226,75,74,.3);
  border-radius: 8px;
  color: #A32D2D;
  font-size: 12px;
  margin-bottom: 14px;
}

/* ═══════════════════════════════════════════════════════════════════
   PHONE MOCKUP (right side, fixed 240×480)
   ═══════════════════════════════════════════════════════════════════ */
.mfa-ob-phone {
  width: 240px; height: 480px;
  background: #1E2A4A; border-radius: 34px;
  padding: 8px; position: relative;
  box-shadow: 0 24px 60px rgba(15,23,60,.25), 0 8px 20px rgba(15,23,60,.12);
}
.mfa-ob-phone-notch {
  position: absolute; top: 12px; left: 50%; transform: translateX(-50%);
  width: 84px; height: 18px; background: #0F1228;
  border-radius: 10px; z-index: 2;
}
.mfa-ob-phone-screen {
  width: 100%; height: 100%;
  background: #17212B; border-radius: 26px;
  overflow: hidden; position: relative;
}
.mfa-ob-phone-halo {
  position: absolute; top: 50%; left: 50%; transform: translate(-50%,-50%);
  width: 200px; height: 200px;
  background: radial-gradient(circle, rgba(29,158,117,.22) 0%, transparent 70%);
  pointer-events: none;
}
.mfa-ob-phone-status {
  padding: 30px 18px 8px;
  display: flex; align-items: center; justify-content: space-between;
  font-size: 10px; color: rgba(255,255,255,.85);
}
.mfa-ob-phone-status-icons { font-size: 10px; }

.mfa-ob-phone-welcome {
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  height: calc(100% - 80px); padding: 16px; gap: 14px;
}
.mfa-ob-phone-logo-card {
  width: 80px; height: 80px; border-radius: 24px;
  background: white; padding: 12px;
  display: flex; align-items: center; justify-content: center;
}
.mfa-ob-phone-bot-name { color: white; font-size: 13px; font-weight: 500; }
.mfa-ob-phone-bot-handle { color: #6AB3F3; font-size: 10px; margin-top: -4px; }
.mfa-ob-phone-cta {
  background: #2B5278; border: none; color: white;
  padding: 9px 24px; border-radius: 18px;
  font-size: 12px; font-weight: 500;
  animation: mfa-gentle 2.4s ease-in-out infinite;
}
@keyframes mfa-gentle { 0%,100% { transform: scale(1); } 50% { transform: scale(1.04); } }

.mfa-ob-phone-chat-hdr {
  padding: 6px 12px;
  background: #232E3C;
  display: flex; align-items: center; gap: 8px;
}
.mfa-ob-phone-avatar {
  width: 28px; height: 28px; border-radius: 50%;
  background: white; padding: 4px;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.mfa-ob-phone-hdr-name { font-size: 11px; color: white; font-weight: 500; line-height: 1.2; }
.mfa-ob-phone-hdr-sub  { font-size: 9px; color: #6AB3F3; line-height: 1.2; }
.mfa-ob-phone-online { color: #4FCC9A; }

.mfa-ob-phone-msgs {
  padding: 12px 10px;
  display: flex; flex-direction: column; gap: 8px;
}
.mfa-ob-phone-msg {
  align-self: flex-start; max-width: 88%;
  background: #182533; color: #E6EBF0;
  padding: 7px 9px; border-radius: 10px 10px 10px 4px;
  font-size: 10px; line-height: 1.4;
}
.mfa-ob-phone-msg-code {
  position: relative; overflow: hidden;
}
.mfa-ob-phone-msg-code::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0;
  height: 3px; background: #7F77DD;
  border-top-left-radius: inherit; border-top-right-radius: inherit;
  animation:
    uzaStripeDrawIn .8s cubic-bezier(0.34, 1.2, 0.64, 1) 100ms both,
    uzaStripeBreathe 2.8s ease-in-out 1s infinite;
  pointer-events: none;
}
.mfa-ob-phone-time {
  font-size: 8px; color: rgba(255,255,255,.4);
  text-align: right; margin-top: 3px;
}
.mfa-ob-phone-card::before { content:""; position:absolute; left:5px; top:4px; bottom:4px; width:3px; border-radius:3px; background:#7F77DD; }
.mfa-ob-phone-card {
  position: relative; overflow: hidden;
  background: rgba(127,119,221,.15);
  padding: 5px 8px 5px 14px;
  margin-top: 5px;
  border-radius: 4px;
}
.mfa-ob-pc-label {
  color: #B0A8F0; font-size: 9px;
  margin-top: 4px; margin-bottom: 1px;
  text-transform: uppercase; letter-spacing: 0.04em;
}
.mfa-ob-pc-label:first-child { margin-top: 0; }
.mfa-ob-pc-value { color: white; font-weight: 500; font-size: 10px; }
.mfa-ob-pc-value.mfa-ob-mono { font-size: 9px; }

.mfa-ob-phone-kbd {
  align-self: flex-start;
  display: flex; flex-direction: column; gap: 4px;
  width: 88%;
}
.mfa-ob-phone-kbd-btn {
  background: #2B5278; border: none; color: white;
  padding: 7px; border-radius: 6px;
  font-size: 10px; font-weight: 500; cursor: pointer;
  text-align: center;
}
.mfa-ob-phone-kbd-btn.pulse { animation: mfa-gentle 2.4s ease-in-out infinite; }
.mfa-ob-phone-kbd-btn.dim { opacity: 0.7; font-weight: 400; }

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
@keyframes mfa-code-reveal {
  from { opacity: 0; letter-spacing: 0.3em; }
  to   { opacity: 1; letter-spacing: 0.12em; }
}
.mfa-ob-phone-code-hint {
  font-size: 9px; color: rgba(255,255,255,.55);
  margin-top: 4px;
}

/* ───── Celebration (step 4) ───── */
.mfa-ob-confetti {
  position: absolute;
  width: 5px; height: 5px;
  animation: mfa-fall 3s linear infinite;
}
.mfa-ob-confetti-1 { top: 60px; left: 30px;  background: #EF9F27; transform: rotate(45deg); animation-delay: .2s; }
.mfa-ob-confetti-2 { top: 40px; right: 40px; background: #7F77DD; border-radius: 50%; animation-delay: .8s; animation-duration: 2.6s; }
.mfa-ob-confetti-3 { top: 70px; left: 50%;   background: #1D9E75; animation-delay: 1.4s; animation-duration: 3.2s; }
.mfa-ob-confetti-4 { top: 50px; right: 60px; background: #E24B4A; width: 4px; height: 8px; animation-delay: .5s; animation-duration: 2.8s; }
@keyframes mfa-fall {
  0%   { transform: translateY(0) rotate(0); opacity: 1; }
  100% { transform: translateY(360px) rotate(360deg); opacity: 0; }
}
.mfa-ob-phone-celebrate {
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  height: calc(100% - 60px); padding: 16px; gap: 14px;
}
.mfa-ob-celebrate-circle {
  width: 86px; height: 86px; border-radius: 50%;
  background: #1D9E75;
  display: flex; align-items: center; justify-content: center;
  box-shadow: 0 0 0 8px rgba(29,158,117,.2), 0 0 0 16px rgba(29,158,117,.08);
  animation: mfa-gentle 2s ease-in-out infinite;
}
.mfa-ob-celebrate-title { color: white; font-size: 14px; font-weight: 500; }
.mfa-ob-celebrate-sub {
  color: rgba(255,255,255,.6); font-size: 10px;
  line-height: 1.4; text-align: center; padding: 0 14px;
}
.mfa-ob-celebrate-footer {
  margin-top: auto;
  display: flex; align-items: center; gap: 6px;
  color: white; font-size: 9px; font-weight: 500;
  opacity: 0.6;
}

/* ───── Step transitions ───── */
.mfa-ob-fade-enter-active,
.mfa-ob-fade-leave-active {
  transition: opacity .35s ease, transform .35s ease;
}
.mfa-ob-fade-enter-from {
  opacity: 0; transform: translateY(12px);
}
.mfa-ob-fade-leave-to {
  opacity: 0; transform: translateY(-8px);
}

/* ───── Responsive: narrower than 880px → stack ───── */
@media (max-width: 880px) {
  .mfa-ob-pane {
    grid-template-columns: 1fr;
    gap: 32px;
    padding: 28px 24px;
  }
  .mfa-ob-right { order: -1; }
}
</style>
