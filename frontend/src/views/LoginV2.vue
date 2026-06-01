<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useRouter, useRoute } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { authApi } from "@/api/auth";
import { mfaApi } from "@/api/mfa";
import { AxiosError } from "axios";
import EptLogo from "@/components/EptLogo.vue";

const router = useRouter();
const route = useRoute();
const auth = useAuthStore();

const login = ref("");
const password = ref("");
const loading = ref(false);
const error = ref<string | null>(null);
const logoRef = ref<InstanceType<typeof EptLogo> | null>(null);

onMounted(() => {
  setTimeout(() => logoRef.value?.replay(), 150);
});

async function handleLogin() {
  if (loading.value) return;
  loading.value = true;
  error.value = null;

  try {
    const resp = await mfaApi.loginMfa(login.value.trim(), password.value);

    if (resp.mfa_required) {
      // Persist challenge in sessionStorage so refresh won't lose it
      sessionStorage.setItem("uza_mfa_challenge", JSON.stringify({
        challenge_id: resp.challenge_id,
        method: resp.method,
        masked_destination: resp.masked_destination,
        ttl_minutes: resp.ttl_minutes ?? 5,
        login: login.value.trim(),
        issued_at: Date.now(),
      }));
      const redirect = (route.query.redirect as string | undefined) ?? "/";
      void router.push({ name: "login-mfa-step", query: { redirect } });
      return;
    }

    // No MFA — full TokenPair returned, proceed normally
    if (!resp.access_token || !resp.refresh_token) {
      throw new Error("Сервер вернул некорректный ответ");
    }
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
    const target = (route.query.redirect as string | undefined) ?? auth.defaultLanding();
    void router.push(target);
  } catch (e) {
    if (e instanceof AxiosError) {
      const status = e.response?.status;
      const detail = e.response?.data?.detail;
      if (status === 401) error.value = detail ?? "Неверный логин или пароль";
      else if (status === 423) error.value = detail ?? "Аккаунт временно заблокирован";
      else if (status === 429) error.value = "Слишком много попыток. Подождите минуту.";
      else if (status === 403) error.value = detail ?? "Аккаунт отключён";
      else if (status === 500) error.value = detail ?? "Внутренняя ошибка сервера";
      else error.value = `Ошибка: ${detail ?? e.message}`;
    } else {
      error.value = "Не удалось подключиться к серверу";
    }
    auth.clear();
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="lg-page">
    <div class="lg-card">
      <div class="lg-logo-wrap">
        <EptLogo ref="logoRef" :size="80" />
      </div>

      <div class="lg-tagline">Единая Платформа Трансформации</div>

      <form @submit.prevent="handleLogin" class="lg-form">
        <div class="lg-field lg-field-1">
          <label class="lg-label">Логин или email</label>
          <input
            v-model="login"
            type="text"
            autocomplete="username"
            :disabled="loading"
            class="uza-input lg-input"
          />
        </div>

        <div class="lg-field lg-field-2">
          <label class="lg-label">Пароль</label>
          <input
            v-model="password"
            type="password"
            autocomplete="current-password"
            :disabled="loading"
            class="uza-input lg-input"
          />
        </div>

        <button
          type="submit"
          :disabled="loading || !login || !password"
          class="lg-btn"
        >
          <span v-if="loading" class="uza-spinner lg-spinner"></span>
          {{ loading ? "Вход…" : "Войти" }}
        </button>
      </form>

      <transition name="uza-fade">
        <div v-if="error" class="lg-err">{{ error }}</div>
      </transition>
    </div>
  </div>
</template>

<style scoped>
/* Match Login.vue style 1:1 */
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
.lg-logo-wrap { display: flex; justify-content: center; margin-bottom: 8px; }
.lg-tagline {
  text-align: center;
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--t3, #64748B);
  margin-bottom: 28px;
}
.lg-form { display: flex; flex-direction: column; gap: 16px; }
.lg-field { display: flex; flex-direction: column; gap: 6px; }
.lg-label {
  font-size: 10px;
  font-weight: 500;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--t3, #64748B);
}
.lg-input {
  height: 44px;
  border-radius: 11px;
  padding: 0 14px;
  font-size: 15px;
  font-weight: 400;
  letter-spacing: -0.01em;
  border: 1px solid rgba(15, 23, 60, 0.12);
  background: var(--bg1, #fff);
  transition: all 0.18s cubic-bezier(0.34, 1.2, 0.64, 1);
}
.lg-input:focus { outline: none; border-color: #7F77DD; box-shadow: 0 0 0 3px rgba(127, 119, 221, 0.18); }
.lg-input:disabled { opacity: 0.55; cursor: not-allowed; }
.lg-btn {
  margin-top: 8px;
  height: 44px;
  border-radius: 11px;
  background: #7F77DD;
  color: #fff;
  font-size: 14px;
  font-weight: 500;
  letter-spacing: 0.02em;
  border: none;
  cursor: pointer;
  transition: all 0.18s cubic-bezier(0.34, 1.2, 0.64, 1);
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
  font-weight: 400;
}
.uza-fade-enter-active, .uza-fade-leave-active { transition: opacity 0.2s; }
.uza-fade-enter-from, .uza-fade-leave-to { opacity: 0; }
</style>
