<script setup lang="ts">
/**
 * ForgotPasswordPage — восстановление пароля через Telegram-код (Pack 152).
 *
 * Шаги (single view, state machine):
 *   1) email/username → POST /auth/forgot-password → reset_id + ttl + masked_tg
 *   2) 6-цифр код + новый пароль x2 → POST /auth/forgot-password/verify
 *   3) Success: auto-login (если без MFA) ИЛИ redirect на /login с MFA-required
 */
import { computed, ref } from "vue";
import { useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { mfaApi } from "@/api/mfa";
import { authApi } from "@/api/auth";
import { api } from "@/api/client";
import { AxiosError } from "axios";
import minfinLogoUrl from "@/assets/minfin-logo-eng.png";
import uzassetsLogoUrl from "@/assets/uzassets-logo-wide.png";

const router = useRouter();
const auth = useAuthStore();

const step = ref<1 | 2 | 3>(1);
const error = ref<string | null>(null);
const busy = ref(false);

const login = ref("");
const resetId = ref("");
const ttlMin = ref(5);
const maskedTg = ref<string | null>(null);
const initMessage = ref("");

const code = ref("");
const newPwd = ref("");
const confirmPwd = ref("");
const showPwd = ref(false);

const canInit = computed(() => login.value.trim().length >= 3 && !busy.value);
const canVerify = computed(() =>
  code.value.replace(/\s/g, "").length === 6 &&
  newPwd.value.length >= 12 &&
  newPwd.value === confirmPwd.value &&
  !busy.value
);

async function submitInit() {
  if (!canInit.value) return;
  busy.value = true;
  error.value = null;
  try {
    const { data } = await api.post<{
      reset_id: string;
      ttl_minutes: number;
      masked_telegram: string | null;
      message: string;
    }>("/auth/forgot-password", { login: login.value.trim() });

    resetId.value = data.reset_id;
    ttlMin.value = data.ttl_minutes ?? 5;
    maskedTg.value = data.masked_telegram;
    initMessage.value = data.message;
    step.value = 2;
  } catch (e) {
    error.value = parseErr(e, "Не удалось отправить код");
  } finally {
    busy.value = false;
  }
}

async function submitVerify() {
  if (!canVerify.value) return;
  busy.value = true;
  error.value = null;
  try {
    const { data } = await api.post<{ ok: boolean; mfa_required: boolean }>(
      "/auth/forgot-password/verify",
      { reset_id: resetId.value, code: code.value.trim(), new_password: newPwd.value },
    );
    if (!data.ok) throw new Error("Не удалось сбросить пароль");
    step.value = 3;

    // Auto-login attempt
    setTimeout(async () => {
      try {
        const resp = await mfaApi.loginMfa(login.value.trim(), newPwd.value);
        if (resp.mfa_required) {
          sessionStorage.setItem("uza_mfa_challenge", JSON.stringify({
            challenge_id: resp.challenge_id,
            method: resp.method,
            masked_destination: resp.masked_destination,
            ttl_minutes: resp.ttl_minutes ?? 5,
            login: login.value.trim(),
            issued_at: Date.now(),
          }));
          router.push({ name: "login-mfa-step", query: { redirect: "/" } });
        } else if (resp.access_token && resp.refresh_token) {
          auth.setTokens({
            access_token: resp.access_token,
            refresh_token: resp.refresh_token,
            token_type: resp.token_type ?? "Bearer",
            expires_in: resp.expires_in ?? 1800,
          });
          const me = await authApi.me();
          auth.setUser(me);
          router.push(auth.defaultLanding());
        } else {
          // fallback
          router.push({ name: "login" });
        }
      } catch {
        router.push({ name: "login" });
      }
    }, 1400);
  } catch (e) {
    error.value = parseErr(e, "Неверный код или истёк срок действия");
  } finally {
    busy.value = false;
  }
}

function backToStep1() {
  step.value = 1;
  error.value = null;
  code.value = "";
  newPwd.value = "";
  confirmPwd.value = "";
}

function parseErr(e: unknown, fallback: string): string {
  if (e instanceof AxiosError) {
    const status = e.response?.status;
    const detail = e.response?.data?.detail;
    if (status === 429) return "Слишком много попыток. Попробуйте через час.";
    if (typeof detail === "string") return detail;
  }
  if (e instanceof Error) return e.message || fallback;
  return fallback;
}
</script>

<template>
  <div class="fp-page">
    <div class="fp-stage">
      <!-- LEFT brand panel -->
      <aside class="fp-brand">
        <div class="fp-brand-group">
          <div class="fp-ministry">
            <img :src="minfinLogoUrl" alt="" class="fp-ministry-emblem"/>
            <div class="fp-ministry-text">
              O'zbekiston Respublikasi<br/>
              Iqtisodiyot va moliya vazirligi
            </div>
          </div>

          <div class="fp-brand-divider" aria-hidden="true"></div>

          <div class="fp-uzassets">
            <img :src="uzassetsLogoUrl" alt="" class="fp-uzassets-icon"/>
            <div class="fp-uzassets-text">UzAssets</div>
          </div>
        </div>
        <div class="fp-footer">© 2026 · O'zbekiston Respublikasi</div>
      </aside>

      <!-- RIGHT form panel -->
      <div class="fp-card">
        <h1 class="fp-title">Восстановление пароля</h1>

        <!-- ─── Step 1: email ─── -->
        <form v-if="step === 1" @submit.prevent="submitInit" class="fp-form">
          <p class="fp-sub">Введите email или логин — код придёт в привязанный Telegram-бот.</p>
          <div class="fp-field">
            <label class="fp-label">Email или логин</label>
            <input v-model="login" type="text" autocomplete="username" :disabled="busy" class="fp-input"/>
          </div>
          <button type="submit" :disabled="!canInit" class="fp-btn">
            <span v-if="busy" class="fp-spinner"></span>
            {{ busy ? "Отправка…" : "Получить код" }}
          </button>
          <RouterLink to="/login" class="fp-link">← К входу</RouterLink>
        </form>

        <!-- ─── Step 2: code + new password ─── -->
        <form v-else-if="step === 2" @submit.prevent="submitVerify" class="fp-form">
          <p class="fp-sub">
            Код отправлен в <strong>{{ maskedTg ?? "Telegram-бот" }}</strong>.
            Действителен <strong>{{ ttlMin }} мин</strong>.
          </p>
          <div class="fp-field">
            <label class="fp-label">Код подтверждения (6 цифр)</label>
            <input v-model="code" type="text" inputmode="numeric" pattern="[0-9]{6}" maxlength="6"
                   class="fp-input fp-input-code" autofocus :disabled="busy"/>
          </div>
          <div class="fp-field">
            <label class="fp-label">Новый пароль</label>
            <div class="fp-input-wrap">
              <input v-model="newPwd" :type="showPwd ? 'text' : 'password'" autocomplete="new-password"
                     :disabled="busy" class="fp-input fp-input-with-eye"/>
              <button type="button" class="fp-eye" :aria-label="showPwd ? 'Скрыть' : 'Показать'" @click="showPwd = !showPwd">
                <svg v-if="!showPwd" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>
                </svg>
                <svg v-else viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/>
                </svg>
              </button>
            </div>
            <div class="fp-hint">Минимум 12 символов</div>
          </div>
          <div class="fp-field">
            <label class="fp-label">Повтор нового пароля</label>
            <input v-model="confirmPwd" type="password" autocomplete="new-password" :disabled="busy"
                   class="fp-input"
                   :class="{ 'fp-input-err': confirmPwd.length > 0 && confirmPwd !== newPwd }"/>
            <div v-if="confirmPwd.length > 0 && confirmPwd !== newPwd" class="fp-hint fp-hint-err">Пароли не совпадают</div>
          </div>
          <button type="submit" :disabled="!canVerify" class="fp-btn">
            <span v-if="busy" class="fp-spinner"></span>
            {{ busy ? "Сохраняем…" : "Сменить пароль" }}
          </button>
          <button type="button" @click="backToStep1" class="fp-link" :disabled="busy">← Запросить новый код</button>
        </form>

        <!-- ─── Step 3: success ─── -->
        <div v-else class="fp-success">
          <div class="fp-check-circle">
            <svg viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="20 6 9 17 4 12"/>
            </svg>
          </div>
          <h2 class="fp-success-title">Пароль изменён</h2>
          <p class="fp-sub">Выполняем вход…</p>
        </div>

        <transition name="uza-fade">
          <div v-if="error" class="fp-err">{{ error }}</div>
        </transition>
      </div>
    </div>
  </div>
</template>

<style scoped>
.fp-page {
  min-height: 100vh;
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
  background-color: #F4F2FF;
  background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 96 96' width='96' height='96'><g fill='none' stroke='%23534AB7' stroke-width='0.6' opacity='0.14'><rect x='18' y='18' width='60' height='60'/><rect x='18' y='18' width='60' height='60' transform='rotate(45 48 48)'/><circle cx='48' cy='48' r='10'/><rect x='-12' y='-12' width='24' height='24' transform='rotate(45 0 0)'/><rect x='84' y='-12' width='24' height='24' transform='rotate(45 96 0)'/><rect x='-12' y='84' width='24' height='24' transform='rotate(45 0 96)'/><rect x='84' y='84' width='24' height='24' transform='rotate(45 96 96)'/><line x1='0' y1='48' x2='18' y2='48'/><line x1='78' y1='48' x2='96' y2='48'/><line x1='48' y1='0' x2='48' y2='18'/><line x1='48' y1='78' x2='48' y2='96'/></g></svg>"), linear-gradient(145deg, #EEF0FF 0%, #F4F2FF 40%, #EBF0FF 100%);
  background-repeat: repeat, no-repeat;
  background-attachment: fixed, fixed;
  overflow: hidden;
  color: var(--t1, #1E2A4A);
}
.fp-stage {
  display: flex;
  align-items: stretch;
  max-width: 1080px;
  width: 100%;
  min-height: 520px;
  background: rgba(255, 255, 255, 0.65);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid rgba(15, 23, 60, 0.08);
  border-radius: 22px;
  overflow: hidden;
  box-shadow: 0 32px 80px rgba(15, 23, 60, 0.12), 0 12px 32px rgba(15, 23, 60, 0.08);
  animation: fpFadeUp 0.7s var(--ease-out) both;
}
@keyframes fpFadeUp { 0% { opacity: 0; transform: translateY(20px); } 100% { opacity: 1; transform: translateY(0); } }

.fp-brand {
  flex: 1 1 0;
  display: grid;
  grid-template-rows: 1fr auto 1fr;
  padding: 48px 56px;
  border-right: 1px solid rgba(15, 23, 60, 0.06);
}
.fp-brand-group { grid-row: 2; display: flex; flex-direction: column; align-items: flex-start; gap: 28px; }
.fp-ministry { display: flex; align-items: flex-end; gap: 20px; }
.fp-ministry-emblem {
  height: 96px; width: 78px;
  object-fit: cover; object-position: left center;
  display: block;
  filter: drop-shadow(0 4px 12px rgba(15, 23, 60, 0.10));
  opacity: 0;
  transform: translateY(-12px) scale(0.96);
  animation: fpEmblemIn 0.7s var(--ease-out) 0.10s forwards;
}
@keyframes fpEmblemIn { 0% { opacity: 0; transform: translateY(-12px) scale(0.96); } 100% { opacity: 1; transform: translateY(0) scale(1); } }
.fp-ministry-text {
  font-size: 18px; font-weight: 600; line-height: 1.4;
  color: var(--t1, #1E2A4A); padding-bottom: 4px;
  opacity: 0;
  transform: translateX(-12px);
  animation: fpMinistryTextIn 0.7s var(--ease-out) 0.30s forwards;
}
@keyframes fpMinistryTextIn { 0% { opacity: 0; transform: translateX(-12px); } 100% { opacity: 1; transform: translateX(0); } }

/* Divider hairline */
.fp-brand-divider {
  width: 320px;
  max-width: 80%;
  height: 1px;
  background: linear-gradient(90deg, rgba(83,74,183,0.55) 0%, rgba(83,74,183,0.28) 50%, transparent 100%);
  transform: scaleX(0);
  transform-origin: left center;
  animation: fpDividerDraw 0.9s var(--ease-out) 0.35s forwards;
}
@keyframes fpDividerDraw { 0% { transform: scaleX(0); opacity: 0; } 100% { transform: scaleX(1); opacity: 1; } }

/* UzAssets composite */
.fp-uzassets { display: flex; align-items: center; gap: 20px; }
.fp-uzassets-icon {
  height: 96px; width: 70px;
  object-fit: cover; object-position: left center;
  display: block;
  filter: drop-shadow(0 4px 12px rgba(15, 23, 60, 0.12));
  opacity: 0;
  transform: translateY(12px) scale(0.92);
  animation: fpUzIconIn 0.7s var(--ease-out) 0.60s forwards;
}
@keyframes fpUzIconIn { 0% { opacity: 0; transform: translateY(12px) scale(0.92); } 100% { opacity: 1; transform: translateY(0) scale(1); } }
.fp-uzassets-text {
  font-size: 48px; font-weight: 600;
  letter-spacing: -0.022em; color: var(--t1, #1E2A4A);
  line-height: 1;
  font-family: 'Inter', 'SF Pro', system-ui, sans-serif;
  opacity: 0;
  transform: translateX(-14px);
  animation: fpUzTextIn 0.7s var(--ease-out) 0.80s forwards;
}
@keyframes fpUzTextIn { 0% { opacity: 0; transform: translateX(-14px); } 100% { opacity: 1; transform: translateX(0); } }
.fp-footer {
  grid-row: 3; align-self: end;
  font-size: 11.5px; color: rgba(15, 23, 60, 0.42); letter-spacing: 0.04em;
}

.fp-card {
  flex: 0 0 460px;
  max-width: 460px;
  padding: 48px 44px 40px;
  background: rgba(255, 255, 255, 0.55);
  backdrop-filter: blur(20px);
  border-left: 0.5px solid rgba(15, 23, 60, 0.08);
  display: flex; flex-direction: column;
}
.fp-title {
  font-size: 22px; font-weight: 700; color: var(--t1, #1E2A4A);
  margin: 0 0 24px 0; letter-spacing: -0.015em;
}
.fp-sub {
  font-size: 13.5px; color: rgba(15, 23, 60, 0.65);
  margin: 0 0 22px 0; line-height: 1.5;
}
.fp-form { display: flex; flex-direction: column; gap: 18px; }
.fp-field { display: flex; flex-direction: column; gap: 8px; }
.fp-label {
  font-size: 10.5px; font-weight: 600; letter-spacing: 0.10em;
  text-transform: uppercase; color: rgba(15, 23, 60, 0.55);
}
.fp-input {
  height: 48px;
  border-radius: 11px;
  padding: 0 14px;
  font-size: 14.5px; color: var(--t1, #1E2A4A);
  border: 1px solid rgba(15, 23, 60, 0.12);
  background: rgba(255, 255, 255, 0.92);
  transition: all 0.18s var(--ease-standard);
  font-family: inherit;
}
.fp-input:focus {
  outline: none;
  border-color: rgba(20, 184, 166, 0.65);
  background: var(--bg1, #fff);
  box-shadow: 0 0 0 3px rgba(20, 184, 166, 0.18);
}
.fp-input:disabled { opacity: 0.5; }
.fp-input-err { border-color: var(--sev-high) !important; }
.fp-input-code {
  text-align: center; letter-spacing: 0.5em;
  font-size: 22px; font-weight: 600;
  padding: 0; height: 56px;
}
.fp-input-with-eye { padding-right: 44px; }
.fp-input-wrap { position: relative; }
.fp-eye {
  position: absolute; right: 8px; top: 50%;
  transform: translateY(-50%);
  width: 30px; height: 30px;
  display: inline-flex; align-items: center; justify-content: center;
  background: transparent; border: none; border-radius: 6px;
  cursor: pointer; color: rgba(15, 23, 60, 0.45);
  transition: color 0.15s, background 0.15s;
}
.fp-eye:hover { color: rgba(20, 184, 166, 0.95); background: rgba(20, 184, 166, 0.08); }

.fp-hint { font-size: 11.5px; color: rgba(15, 23, 60, 0.5); }
.fp-hint-err { color: #C53737; }

.fp-btn {
  margin-top: 6px;
  height: 50px;
  border-radius: 12px;
  background: linear-gradient(90deg, #14B8A6 0%, #4F46E5 100%);
  background-size: 200% 100%; background-position: 0% 50%;
  color: #fff; font-size: 15px; font-weight: 600;
  border: none; cursor: pointer;
  display: flex; align-items: center; justify-content: center; gap: 10px;
  transition: background-position 0.4s ease, transform 0.18s, box-shadow 0.18s;
  box-shadow: 0 10px 28px rgba(20, 184, 166, 0.20), 0 4px 14px rgba(79, 70, 229, 0.20);
}
.fp-btn:hover:not(:disabled) {
  background-position: 100% 50%;
  transform: translateY(-1px);
  box-shadow: 0 14px 34px rgba(79, 70, 229, 0.30), 0 6px 18px rgba(20, 184, 166, 0.20);
}
.fp-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.fp-spinner {
  width: 16px; height: 16px;
  border: 2px solid rgba(255,255,255,0.4); border-top-color: #fff;
  border-radius: 50%; animation: fpSpin 0.7s linear infinite;
}
@keyframes fpSpin { to { transform: rotate(360deg); } }

.fp-link {
  display: inline-block; text-align: center; margin-top: 8px;
  font-size: 13px; color: var(--p-deep); text-decoration: none;
  background: none; border: none; cursor: pointer;
  font-family: inherit;
}
.fp-link:hover { color: #7F77DD; text-decoration: underline; }

.fp-err {
  margin-top: 14px; padding: 12px 16px;
  border-radius: 10px;
  background: rgba(226, 75, 74, 0.08); border: 1px solid rgba(226, 75, 74, 0.25);
  color: #C53737; font-size: 13px;
}

.fp-success { text-align: center; padding: 32px 0; }
.fp-check-circle {
  width: 72px; height: 72px; margin: 0 auto 16px;
  display: flex; align-items: center; justify-content: center;
  border-radius: 50%;
  background: rgba(20, 184, 166, 0.12);
  color: #14B8A6;
  animation: fpPop 0.4s cubic-bezier(.34, 1.4, .64, 1) both;
}
@keyframes fpPop { 0% { transform: scale(0); } 100% { transform: scale(1); } }
.fp-success-title {
  font-size: 18px; font-weight: 700; color: var(--t1, #1E2A4A);
  margin: 0 0 6px 0;
}

@media (max-width: 980px) {
  .fp-stage { flex-direction: column; min-height: auto; }
  .fp-brand { padding: 32px 28px; border-right: none; border-bottom: 1px solid rgba(15,23,60,.06); }
  .fp-brand { grid-template-rows: auto; }
  .fp-brand-group { grid-row: auto; gap: 20px; }
  .fp-footer { grid-row: auto; padding-top: 20px; }
  .fp-card { flex: 0 0 auto; max-width: none; width: 100%; padding: 32px 28px; }
}
@media (prefers-reduced-motion: reduce) {
  .fp-stage, .fp-check-circle { animation-duration: 0.01s !important; }
}
</style>
