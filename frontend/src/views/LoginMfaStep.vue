<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from "vue";
import { useRouter, useRoute } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { authApi } from "@/api/auth";
import { mfaApi } from "@/api/mfa";
import { AxiosError } from "axios";

interface StoredChallenge {
  challenge_id: string;
  method: "telegram" | "totp" | "both";
  masked_destination: string;
  ttl_minutes: number;
  login: string;
  issued_at: number;
}

const router = useRouter();
const route = useRoute();
const auth = useAuthStore();

const challenge = ref<StoredChallenge | null>(null);
const digits = ref<string[]>(["", "", "", "", "", ""]);
const inputRefs = ref<HTMLInputElement[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);

// Mode toggle: 'code' (6 digits) or 'recovery'
const mode = ref<"code" | "recovery">("code");
const recoveryCode = ref("");

// Countdown
const elapsed = ref(0);  // seconds since challenge issued
let elapsedTimer: number | null = null;
const ttlSeconds = computed(() => (challenge.value?.ttl_minutes ?? 5) * 60);
const remaining = computed(() => Math.max(0, ttlSeconds.value - elapsed.value));
const mmss = computed(() => {
  const m = Math.floor(remaining.value / 60);
  const s = remaining.value % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
});
const expired = computed(() => remaining.value <= 0);

onMounted(() => {
  const raw = sessionStorage.getItem("uza_mfa_challenge");
  if (!raw) {
    void router.replace({ name: "login-v2" });
    return;
  }
  try {
    challenge.value = JSON.parse(raw) as StoredChallenge;
    elapsed.value = Math.floor((Date.now() - challenge.value.issued_at) / 1000);
    elapsedTimer = window.setInterval(() => {
      elapsed.value++;
    }, 1000);
    nextTick(() => inputRefs.value[0]?.focus());
  } catch {
    sessionStorage.removeItem("uza_mfa_challenge");
    void router.replace({ name: "login-v2" });
  }
});

onBeforeUnmount(() => {
  if (elapsedTimer) clearInterval(elapsedTimer);
});

// ─── Digit input handling ────────────────────────────────────────────────

function onDigitInput(idx: number, ev: Event) {
  const input = ev.target as HTMLInputElement;
  const value = input.value.replace(/\D/g, "");
  if (!value) {
    digits.value[idx] = "";
    return;
  }
  // If user pasted multiple digits, distribute them
  if (value.length > 1) {
    const chars = value.split("").slice(0, 6 - idx);
    chars.forEach((c, i) => {
      digits.value[idx + i] = c;
    });
    const lastFilled = Math.min(idx + chars.length - 1, 5);
    nextTick(() => inputRefs.value[lastFilled]?.focus());
  } else {
    digits.value[idx] = value;
    if (idx < 5) {
      nextTick(() => inputRefs.value[idx + 1]?.focus());
    }
  }
  // Auto-submit when all 6 filled
  if (digits.value.every((d) => d.length === 1)) {
    void handleVerify();
  }
}

function onDigitKeydown(idx: number, ev: KeyboardEvent) {
  if (ev.key === "Backspace" && !digits.value[idx] && idx > 0) {
    digits.value[idx - 1] = "";
    inputRefs.value[idx - 1]?.focus();
    ev.preventDefault();
  } else if (ev.key === "ArrowLeft" && idx > 0) {
    inputRefs.value[idx - 1]?.focus();
    ev.preventDefault();
  } else if (ev.key === "ArrowRight" && idx < 5) {
    inputRefs.value[idx + 1]?.focus();
    ev.preventDefault();
  }
}

function onPaste(ev: ClipboardEvent) {
  const pasted = (ev.clipboardData?.getData("text") || "").replace(/\D/g, "").slice(0, 6);
  if (!pasted) return;
  ev.preventDefault();
  for (let i = 0; i < 6; i++) digits.value[i] = pasted[i] ?? "";
  const lastFilled = Math.min(pasted.length - 1, 5);
  nextTick(() => inputRefs.value[lastFilled]?.focus());
  if (digits.value.every((d) => d.length === 1)) {
    void handleVerify();
  }
}

// ─── Verify ──────────────────────────────────────────────────────────────

async function handleVerify() {
  if (loading.value || !challenge.value) return;
  if (mode.value === "code" && digits.value.some((d) => !d)) return;
  if (mode.value === "recovery" && recoveryCode.value.trim().length < 8) return;

  loading.value = true;
  error.value = null;

  try {
    const payload =
      mode.value === "code"
        ? { challenge_id: challenge.value.challenge_id, code: digits.value.join("") }
        : { login: challenge.value.login, recovery_code: recoveryCode.value.trim() };

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
  } catch (e) {
    if (e instanceof AxiosError) {
      const status = e.response?.status;
      const detail = e.response?.data?.detail;
      if (status === 401) error.value = detail ?? "Неверный код";
      else if (status === 429) error.value = "Слишком много попыток. Подождите минуту.";
      else if (status === 400) error.value = detail ?? "Некорректный запрос";
      else error.value = `Ошибка: ${detail ?? e.message}`;
    } else {
      error.value = "Не удалось подключиться к серверу";
    }
    // Clear digits on failure so user types again
    if (mode.value === "code") {
      digits.value = ["", "", "", "", "", ""];
      nextTick(() => inputRefs.value[0]?.focus());
    }
  } finally {
    loading.value = false;
  }
}

function toggleMode() {
  mode.value = mode.value === "code" ? "recovery" : "code";
  error.value = null;
  if (mode.value === "code") {
    digits.value = ["", "", "", "", "", ""];
    nextTick(() => inputRefs.value[0]?.focus());
  }
}

function backToLogin() {
  sessionStorage.removeItem("uza_mfa_challenge");
  void router.push({ name: "login-v2" });
}
</script>

<template>
  <div class="lg-page">
    <div class="lg-card">
      <div class="mfa-icon">
        <svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="#7F77DD" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <rect x="3" y="11" width="18" height="11" rx="2"/>
          <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
        </svg>
      </div>

      <div class="mfa-title">Подтверждение входа</div>
      <div class="mfa-sub" v-if="challenge && mode === 'code'">
        Код отправлен в {{ challenge.masked_destination }}
      </div>
      <div class="mfa-sub" v-if="mode === 'recovery'">
        Введите один из ваших recovery-кодов
      </div>

      <!-- ─── Code input mode ─── -->
      <div v-if="mode === 'code'" class="mfa-form">
        <div class="mfa-digits" @paste="onPaste">
          <input
            v-for="(d, i) in digits"
            :key="i"
            :ref="(el: any) => { if (el) inputRefs[i] = el; }"
            v-model="digits[i]"
            type="text"
            inputmode="numeric"
            maxlength="1"
            autocomplete="one-time-code"
            class="mfa-digit"
            :disabled="loading || expired"
            @input="onDigitInput(i, $event)"
            @keydown="onDigitKeydown(i, $event)"
          />
        </div>

        <div class="mfa-timer" :class="{ 'mfa-timer-expired': expired }">
          <span v-if="!expired">Срок действия кода: {{ mmss }}</span>
          <span v-else>Код истёк. Вернитесь к шагу входа.</span>
        </div>

        <button
          class="lg-btn"
          :disabled="loading || expired || digits.some((d) => !d)"
          @click="handleVerify"
        >
          <span v-if="loading" class="uza-spinner lg-spinner"></span>
          {{ loading ? "Проверка…" : "Подтвердить" }}
        </button>
      </div>

      <!-- ─── Recovery code mode ─── -->
      <div v-else class="mfa-form">
        <input
          v-model="recoveryCode"
          type="text"
          placeholder="XXXX-XXXX"
          autocomplete="off"
          class="uza-input lg-input mfa-recovery-input"
          :disabled="loading"
          @keydown.enter="handleVerify"
        />
        <button
          class="lg-btn"
          :disabled="loading || recoveryCode.trim().length < 8"
          @click="handleVerify"
        >
          <span v-if="loading" class="uza-spinner lg-spinner"></span>
          {{ loading ? "Проверка…" : "Подтвердить" }}
        </button>
      </div>

      <transition name="uza-fade">
        <div v-if="error" class="lg-err">{{ error }}</div>
      </transition>

      <div class="mfa-links">
        <button type="button" class="mfa-link" @click="toggleMode">
          {{ mode === "code" ? "Использовать recovery-код" : "Ввести код из Telegram" }}
        </button>
        <span class="mfa-sep">·</span>
        <button type="button" class="mfa-link" @click="backToLogin">
          Назад
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.lg-page {
  min-height: 100vh;
  flex: 1 1 0%;
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
  background: linear-gradient(145deg, #EEF0FF 0%, #F4F2FF 40%, #EBF0FF 100%);
  background-attachment: fixed;
}
.lg-card {
  width: 100%;
  max-width: 420px;
  padding: 36px 32px 32px;
  background: rgba(255, 255, 255, 0.85);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(15, 23, 60, 0.08);
  border-radius: 18px;
  box-shadow: 0 24px 64px rgba(15, 23, 60, 0.10), 0 8px 24px rgba(15, 23, 60, 0.06);
}
.mfa-icon { display: flex; justify-content: center; margin-bottom: 8px; }
.mfa-title {
  text-align: center;
  font-size: 15px;
  font-weight: 500;
  letter-spacing: -0.01em;
  color: #0F172A;
  margin-bottom: 4px;
}
.mfa-sub {
  text-align: center;
  font-size: 13px;
  font-weight: 400;
  color: #64748B;
  margin-bottom: 26px;
}
.mfa-form { display: flex; flex-direction: column; gap: 14px; }
.mfa-digits { display: flex; gap: 8px; justify-content: center; }
.mfa-digit {
  width: 44px;
  height: 52px;
  text-align: center;
  font-size: 22px;
  font-weight: 400;
  letter-spacing: -0.025em;
  border-radius: 11px;
  border: 1px solid rgba(15, 23, 60, 0.12);
  background: #fff;
  transition: all 0.18s cubic-bezier(.34, 1.2, .64, 1);
}
.mfa-digit:focus { outline: none; border-color: #7F77DD; box-shadow: 0 0 0 3px rgba(127, 119, 221, 0.18); }
.mfa-digit:disabled { opacity: 0.55; }
.mfa-timer {
  text-align: center;
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: #64748B;
}
.mfa-timer-expired { color: #E24B4A; }
.lg-input { height: 44px; border-radius: 11px; padding: 0 14px; font-size: 15px; border: 1px solid rgba(15, 23, 60, 0.12); background: #fff; }
.lg-input:focus { outline: none; border-color: #7F77DD; box-shadow: 0 0 0 3px rgba(127, 119, 221, 0.18); }
.mfa-recovery-input { text-align: center; letter-spacing: 0.1em; text-transform: uppercase; }
.lg-btn {
  margin-top: 4px;
  height: 44px;
  border-radius: 11px;
  background: #7F77DD;
  color: #fff;
  font-size: 14px;
  font-weight: 500;
  letter-spacing: 0.02em;
  border: none;
  cursor: pointer;
  transition: all 0.18s cubic-bezier(.34, 1.2, .64, 1);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
}
.lg-btn:hover:not(:disabled) { background: #6C5CE7; transform: translateY(-1px); box-shadow: 0 8px 18px rgba(108, 92, 231, 0.28); }
.lg-btn:disabled { opacity: 0.45; cursor: not-allowed; }
.lg-spinner { width: 14px; height: 14px; border: 2px solid rgba(255, 255, 255, 0.4); border-top-color: #fff; border-radius: 50%; animation: spin 0.7s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.lg-err {
  margin-top: 14px;
  padding: 10px 14px;
  border-radius: 10px;
  background: rgba(239, 68, 68, 0.08);
  border: 1px solid rgba(239, 68, 68, 0.22);
  color: #B91C1C;
  font-size: 13px;
}
.mfa-links { margin-top: 18px; display: flex; align-items: center; justify-content: center; gap: 8px; }
.mfa-link {
  background: none; border: none; cursor: pointer;
  font-size: 12px; font-weight: 500;
  color: #7F77DD;
  padding: 4px 6px;
  transition: color 0.15s;
}
.mfa-link:hover { color: #6C5CE7; }
.mfa-sep { color: #94A3B8; font-size: 12px; }
.uza-fade-enter-active, .uza-fade-leave-active { transition: opacity 0.2s; }
.uza-fade-enter-from, .uza-fade-leave-to { opacity: 0; }
</style>
