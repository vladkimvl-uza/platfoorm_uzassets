<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useRouter, useRoute } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { authApi } from "@/api/auth";
import { mfaApi } from "@/api/mfa";
import { AxiosError } from "axios";
import EptLogo from "@/components/EptLogo.vue";
import minfinLogoUrl from "@/assets/minfin-logo-eng.png";
import uzassetsLogoUrl from "@/assets/uzassets-logo-wide.png";

const router = useRouter();
const route = useRoute();
const auth = useAuthStore();

const login = ref("");
const password = ref("");
const showPwd = ref(false);
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
    const target = (route.query.redirect as string | undefined) ?? "/";
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
    <div class="lg-stage">
      <!-- ───── LEFT: brand panel (slides in from LEFT) ───── -->
      <aside class="lg-brand">
        <!-- Centered brand group: ministry — hairline — uzassets.
             Оба блока используют одинаковую grid-сетку (88px icon column +
             text), поэтому тексты выровнены по одной вертикали. -->
        <div class="lg-brand-group">
          <div class="lg-ministry">
            <img :src="minfinLogoUrl" alt="" class="lg-ministry-emblem"/>
            <div class="lg-ministry-text">
              O'zbekiston Respublikasi<br/>
              Iqtisodiyot va moliya vazirligi
            </div>
          </div>

          <div class="lg-brand-divider" aria-hidden="true"></div>

          <div class="lg-uzassets">
            <img :src="uzassetsLogoUrl" alt="" class="lg-uzassets-icon"/>
            <div class="lg-uzassets-text">UzAssets</div>
          </div>
        </div>

        <!-- Footer pinned to bottom -->
        <div class="lg-footer">© 2026 · O'zbekiston Respublikasi</div>
      </aside>

      <!-- ───── RIGHT: login card (slides in from RIGHT) ───── -->
      <div class="lg-card">
        <div class="lg-card-head">
          <EptLogo ref="logoRef" :size="44" />
          <h1 class="lg-card-title">Единая платформа<br/>трансформации</h1>
        </div>

        <form @submit.prevent="handleLogin" class="lg-form">
          <div class="lg-field">
            <label class="lg-label">Логин или email</label>
            <input
              v-model="login"
              type="text"
              autocomplete="username"
              :disabled="loading"
              class="lg-input"
            />
          </div>

          <div class="lg-field">
            <label class="lg-label">Пароль</label>
            <div class="lg-input-wrap">
              <input
                v-model="password"
                :type="showPwd ? 'text' : 'password'"
                autocomplete="current-password"
                :disabled="loading"
                class="lg-input lg-input-with-eye"
              />
              <button type="button" class="lg-eye" :aria-label="showPwd ? 'Скрыть пароль' : 'Показать пароль'" @click="showPwd = !showPwd">
                <svg v-if="!showPwd" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>
                </svg>
                <svg v-else viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/>
                </svg>
              </button>
            </div>
          </div>

          <button
            type="submit"
            :disabled="loading || !login || !password"
            class="lg-btn"
          >
            <span v-if="loading" class="lg-spinner"></span>
            {{ loading ? "Вход…" : "Войти" }}
          </button>

          <RouterLink class="lg-forgot" to="/forgot-password">Забыли пароль?</RouterLink>
        </form>

        <transition name="uza-fade">
          <div v-if="error" class="lg-err">{{ error }}</div>
        </transition>
      </div>
    </div>

  </div>
</template>

<style scoped>
/* ════════════════════════════════════════════════════════════════
   Dark navy login — концепт от пользователя.
   Функционал handleLogin / MFA / error остался 1:1, переписан только
   layout + цвета.
   ════════════════════════════════════════════════════════════════ */
/* Гирих-паттерн (Islamic geometric tile): 8-pointed star из двух
   наложенных rotated квадратов + угловые звёздочки → seamless tile 96px.
   stroke #7F9CE8 / 0.6px / opacity 0.08 (вся группа). Inline SVG → data URI. */
/* ── Light theme ── */
.lg-page {
  min-height: 100vh;
  flex: 1 1 0%;
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
  background-color: #F4F2FF;
  background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 96 96' width='96' height='96'><g fill='none' stroke='%23534AB7' stroke-width='0.6' opacity='0.14'><rect x='18' y='18' width='60' height='60'/><rect x='18' y='18' width='60' height='60' transform='rotate(45 48 48)'/><circle cx='48' cy='48' r='10'/><rect x='-12' y='-12' width='24' height='24' transform='rotate(45 0 0)'/><rect x='84' y='-12' width='24' height='24' transform='rotate(45 96 0)'/><rect x='-12' y='84' width='24' height='24' transform='rotate(45 0 96)'/><rect x='84' y='84' width='24' height='24' transform='rotate(45 96 96)'/><line x1='0' y1='48' x2='18' y2='48'/><line x1='78' y1='48' x2='96' y2='48'/><line x1='48' y1='0' x2='48' y2='18'/><line x1='48' y1='78' x2='48' y2='96'/></g></svg>"),
                    linear-gradient(145deg, #EEF0FF 0%, #F4F2FF 40%, #EBF0FF 100%);
  background-repeat: repeat, no-repeat;
  background-attachment: fixed, fixed;
  overflow: hidden;
  color: #1E2A4A;
}

/* Two-column light glass stage */
.lg-stage {
  display: flex;
  align-items: stretch;
  gap: 0;
  max-width: 1180px;
  width: 100%;
  min-height: 620px;
  background: rgba(255, 255, 255, 0.65);
  border: 1px solid rgba(15, 23, 60, 0.08);
  border-radius: 22px;
  overflow: hidden;
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  box-shadow: 0 32px 80px rgba(15, 23, 60, 0.12), 0 12px 32px rgba(15, 23, 60, 0.08);
}

/* ───── LEFT: brand panel — enterprise grid layout ─────
   3-row grid (1fr / auto / 1fr): brand-group центрирован вертикально,
   footer в нижнем 1fr с align-self:end. Все логотипы выровнены по одной
   icon-колонке 88px → тексты Ministry и UzAssets начинаются на одной X. */
.lg-brand {
  flex: 1 1 0;
  display: grid;
  grid-template-rows: 1fr auto 1fr;
  padding: 56px 64px;
  min-width: 0;
  border-right: 1px solid rgba(15, 23, 60, 0.06);
  animation: lgSlideInLeft 0.7s cubic-bezier(0.22, 1, 0.36, 1) both;
}

.lg-brand-group {
  grid-row: 2;
  display: flex;
  flex-direction: column;
  align-items: flex-start;  /* всё выровнено по левому краю */
  gap: 40px;
}

/* Ministry: emblem + 2-line title-case text (выровнен по низу герба) */
.lg-ministry {
  display: flex;
  align-items: flex-end;        /* baseline по нижней границе логотипа */
  gap: 20px;
}
.lg-ministry-text {
  font-size: 18px;              /* +20% от 15px */
  font-weight: 600;
  letter-spacing: 0.005em;
  line-height: 1.4;
  color: #1E2A4A;
  padding-bottom: 4px;          /* небольшой optical baseline align */
  opacity: 0;
  transform: translateX(-12px);
  animation: lgMinistryTextIn 0.7s cubic-bezier(0.22, 1, 0.36, 1) 0.30s forwards;
}
@keyframes lgMinistryTextIn {
  0%   { opacity: 0; transform: translateX(-12px); }
  100% { opacity: 1; transform: translateX(0); }
}
.lg-ministry-emblem {
  /* Native PNG ~3.5:1; герб ~22% слева. При height:96px scaled-width =
     ~336px; чтобы показать ТОЛЬКО герб без текста — width ≤ 75px. */
  height: 96px;
  width: 78px;
  object-fit: cover;
  object-position: left center;
  display: block;
  filter: drop-shadow(0 4px 12px rgba(15, 23, 60, 0.10));
  opacity: 0;
  transform: translateY(-12px) scale(0.96);
  animation: lgEmblemIn 0.7s cubic-bezier(0.22, 1, 0.36, 1) 0.10s forwards;
}
@keyframes lgEmblemIn {
  0%   { opacity: 0; transform: translateY(-12px) scale(0.96); }
  100% { opacity: 1; transform: translateY(0) scale(1); }
}

/* Тонкая разделительная линия — выровнена влево как логотипы, draw-in от левого края */
.lg-brand-divider {
  width: 320px;
  max-width: 80%;
  height: 1px;
  background: linear-gradient(90deg,
    rgba(83, 74, 183, 0.55) 0%,
    rgba(83, 74, 183, 0.28) 50%,
    transparent 100%);
  transform: scaleX(0);
  transform-origin: left center;
  animation: lgDividerDraw 0.9s cubic-bezier(0.22, 1, 0.36, 1) 0.35s forwards;
}
@keyframes lgDividerDraw {
  0%   { transform: scaleX(0); opacity: 0; }
  100% { transform: scaleX(1); opacity: 1; }
}

/* UzAssets composite — U-icon + bold text, staggered draw-in */
.lg-uzassets {
  display: flex;
  align-items: center;
  gap: 20px;
}
.lg-uzassets-icon {
  /* UzAssets PNG: U-mark в левых ~22-25%. Cropping width ~75px чтобы
     не показывать начало "U" из текста PNG. */
  height: 96px;
  width: 70px;
  object-fit: cover;
  object-position: left center;
  display: block;
  filter: drop-shadow(0 4px 12px rgba(15, 23, 60, 0.12));
  opacity: 0;
  transform: translateY(12px) scale(0.92);
  animation: lgUzIconIn 0.7s cubic-bezier(0.22, 1, 0.36, 1) 0.60s forwards;
}
@keyframes lgUzIconIn {
  0%   { opacity: 0; transform: translateY(12px) scale(0.92); }
  100% { opacity: 1; transform: translateY(0) scale(1); }
}
.lg-uzassets-text {
  font-size: 48px;            /* 60 - 20% */
  font-weight: 600;
  letter-spacing: -0.022em;
  color: #1E2A4A;
  line-height: 1;
  font-family: 'Inter', 'SF Pro', system-ui, sans-serif;
  opacity: 0;
  transform: translateX(-14px);
  animation: lgUzTextIn 0.7s cubic-bezier(0.22, 1, 0.36, 1) 0.80s forwards;
}
@keyframes lgUzTextIn {
  0%   { opacity: 0; transform: translateX(-14px); }
  100% { opacity: 1; transform: translateX(0); }
}

@media (prefers-reduced-motion: reduce) {
  .lg-ministry-emblem,
  .lg-ministry-text,
  .lg-uzassets-icon,
  .lg-uzassets-text,
  .lg-brand-divider {
    animation-duration: 0.01s !important;
    opacity: 1 !important;
    transform: none !important;
  }
}

.lg-footer {
  grid-row: 3;
  align-self: end;
  font-size: 11.5px;
  color: rgba(15, 23, 60, 0.42);
  letter-spacing: 0.04em;
}

/* ───── RIGHT: login card (light glass) ───── */
.lg-card {
  flex: 0 0 480px;
  max-width: 480px;
  padding: 56px 56px 48px;
  background: rgba(255, 255, 255, 0.55);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border-left: 0.5px solid rgba(15, 23, 60, 0.08);
  align-self: stretch;
  display: flex;
  flex-direction: column;
  animation: lgSlideInRight 0.7s cubic-bezier(0.22, 1, 0.36, 1) both;
}
@supports not ((backdrop-filter: blur(20px)) or (-webkit-backdrop-filter: blur(20px))) {
  .lg-card { background: rgba(255, 255, 255, 0.92); }
}
.lg-card-head {
  display: flex;
  align-items: center;
  gap: 14px;
  margin: 0 0 32px 0;
}
.lg-card-title {
  font-size: 22px;
  font-weight: 700;
  margin: 0;
  color: #1E2A4A;
  letter-spacing: -0.015em;
  line-height: 1.1;
}
/* lg-card-sub удалён — пользователь убрал "Введите учётные данные".
   Spacing к форме теперь через card-head + form gap. */

/* ─── Side-slide animations ─── */
@keyframes lgSlideInLeft {
  0%   { opacity: 0; transform: translateX(-60px); }
  100% { opacity: 1; transform: translateX(0); }
}
@keyframes lgSlideInRight {
  0%   { opacity: 0; transform: translateX(60px); }
  100% { opacity: 1; transform: translateX(0); }
}
@keyframes lgDividerGrow {
  0%   { opacity: 0; transform: scaleY(0); }
  100% { opacity: 1; transform: scaleY(1); }
}

/* ─── Responsive: stack vertically on small screens ─── */
@media (max-width: 980px) {
  .lg-stage { flex-direction: column; min-height: auto; }
  .lg-brand {
    padding: 32px 28px;
    border-right: none;
    border-bottom: 1px solid rgba(255, 255, 255, 0.05);
  }
  .lg-ministry-emblem { height: 48px; width: 42px; }
  .lg-ministry-text { font-size: 10.5px; }
  .lg-uzassets { margin: 24px 0 0; gap: 12px; }
  .lg-uzassets-icon { height: 60px; width: 54px; }
  .lg-uzassets-text { font-size: 36px; }
  .lg-card { flex: 0 0 auto; max-width: none; width: 100%; padding: 36px 28px 32px; }
  .lg-card-title { font-size: 19px; }
}

/* ─── Reduced motion ─── */
@media (prefers-reduced-motion: reduce) {
  .lg-brand, .lg-card, .lg-divider {
    animation-duration: 0.01s !important;
  }
}
.lg-form { display: flex; flex-direction: column; gap: 22px; }
.lg-field { display: flex; flex-direction: column; gap: 10px; }
.lg-label {
  font-size: 10.5px;
  font-weight: 600;
  letter-spacing: 0.10em;
  text-transform: uppercase;
  color: rgba(15, 23, 60, 0.55);
}
.lg-input {
  height: 50px;
  border-radius: 12px;
  padding: 0 16px;
  font-size: 14.5px;
  font-weight: 400;
  letter-spacing: -0.005em;
  color: #1E2A4A;
  border: 1px solid rgba(15, 23, 60, 0.12);
  background: rgba(255, 255, 255, 0.92);
  transition: all 0.18s cubic-bezier(0.34, 1.2, 0.64, 1);
  font-family: inherit;
}
.lg-input::placeholder { color: rgba(15, 23, 60, 0.30); }
.lg-input-with-eye { padding-right: 44px; }
.lg-input-wrap { position: relative; display: block; }
.lg-eye {
  position: absolute;
  right: 8px;
  top: 50%;
  transform: translateY(-50%);
  width: 32px;
  height: 32px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  padding: 0;
  color: rgba(15, 23, 60, 0.45);
  transition: color 0.15s, background 0.15s;
}
.lg-eye:hover { color: rgba(20, 184, 166, 0.95); background: rgba(20, 184, 166, 0.08); }
.lg-input:focus {
  /* Бирюзовая обводка + glow */
  outline: none;
  border-color: rgba(20, 184, 166, 0.65);
  background: #ffffff;
  box-shadow: 0 0 0 3px rgba(20, 184, 166, 0.18);
}
.lg-input:disabled { opacity: 0.5; cursor: not-allowed; }

.lg-btn {
  margin-top: 10px;
  height: 54px;
  border-radius: 13px;
  /* Teal → indigo gradient (как в концепте) */
  background: linear-gradient(90deg, #14B8A6 0%, #4F46E5 100%);
  background-size: 200% 100%;
  background-position: 0% 50%;
  color: #fff;
  font-size: 15.5px;
  font-weight: 600;
  letter-spacing: 0.01em;
  border: none;
  cursor: pointer;
  transition: background-position 0.4s ease, transform 0.18s cubic-bezier(0.34, 1.2, 0.64, 1), box-shadow 0.18s ease;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  box-shadow: 0 10px 28px rgba(20, 184, 166, 0.20), 0 4px 14px rgba(79, 70, 229, 0.20);
}
.lg-btn:hover:not(:disabled) {
  background-position: 100% 50%;
  transform: translateY(-1px);
  box-shadow: 0 14px 34px rgba(79, 70, 229, 0.30), 0 6px 18px rgba(20, 184, 166, 0.20);
}
.lg-btn:disabled { opacity: 0.40; cursor: not-allowed; }

.lg-spinner {
  width: 16px; height: 16px;
  border: 2px solid rgba(255, 255, 255, 0.4);
  border-top-color: #fff;
  border-radius: 50%;
  animation: lgSpin 0.7s linear infinite;
}
@keyframes lgSpin { to { transform: rotate(360deg); } }

.lg-forgot {
  display: block;
  text-align: center;
  font-size: 13px;
  color: #534AB7;
  text-decoration: none;
  margin-top: 6px;
  transition: color 0.15s;
}
.lg-forgot:hover { color: #7F77DD; text-decoration: underline; }

.lg-err {
  margin-top: 16px;
  padding: 12px 16px;
  border-radius: 11px;
  background: rgba(226, 75, 74, 0.08);
  border: 1px solid rgba(226, 75, 74, 0.25);
  color: #C53737;
  font-size: 13px;
  font-weight: 400;
}
.uza-fade-enter-active, .uza-fade-leave-active { transition: opacity 0.2s; }
.uza-fade-enter-from, .uza-fade-leave-to { opacity: 0; }
</style>
