<script setup lang="ts">
/**
 * ChangePasswordPage — self-service password change.
 *
 * Two contexts:
 *   1. Forced (must_change_password === true) — router guard sends user here
 *      from any other route. Header shows "Требуется смена пароля".
 *   2. Voluntary — accessed via profile menu. Header shows "Смена пароля".
 *
 * On success → updates auth.user.must_change_password = false and redirects:
 *   forced  → /  (or last attempted route in router-guard state)
 *   voluntary → /profile/security  (or wherever they came from)
 */
import { computed, ref } from "vue";
import { useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { authApi } from "@/api/auth";

const router = useRouter();
const auth = useAuthStore();

const isForced = computed(() => auth.user?.must_change_password === true);

const currentPwd = ref("");
const newPwd = ref("");
const confirmPwd = ref("");

const showCurrent = ref(false);
const showNew = ref(false);
const showConfirm = ref(false);

const submitting = ref(false);
const submitError = ref<string | null>(null);

// Live policy checks
const checks = computed(() => {
  const p = newPwd.value;
  return {
    length:    p.length >= 12,
    upper:     /[A-Z]/.test(p),
    lower:     /[a-z]/.test(p),
    digit:     /[0-9]/.test(p),
    special:   /[^A-Za-z0-9]/.test(p),
    no_repeat: !/(.)\1\1/.test(p),
    no_seq:    !/(?:0123|1234|2345|3456|4567|5678|6789|abcd|bcde|cdef|defg|qwer|wert|erty|rtyu|asdf|sdfg|dfgh|zxcv|xcvb)/i.test(p),
    no_common: !/^(password|qwerty|123456|admin|letmein|welcome|uzbekistan|tashkent|123123)/i.test(p),
  };
});

const passedCount = computed(() => Object.values(checks.value).filter(Boolean).length);
const strength = computed(() => {
  // 0-8 → 0..100
  if (newPwd.value.length === 0) return 0;
  return Math.round((passedCount.value / 8) * 100);
});
const strengthLabel = computed(() => {
  if (strength.value === 0) return "—";
  if (strength.value < 50) return "слабый";
  if (strength.value < 80) return "средний";
  if (strength.value < 100) return "хороший";
  return "сильный";
});
const strengthColor = computed(() => {
  if (strength.value < 50) return "#E24B4A";
  if (strength.value < 80) return "#EF9F27";
  if (strength.value < 100) return "#7F77DD";
  return "#1D9E75";
});

const confirmOk = computed(() => confirmPwd.value.length > 0 && confirmPwd.value === newPwd.value);
const allChecksPassed = computed(() => Object.values(checks.value).every(Boolean));

const canSubmit = computed(() =>
  !submitting.value &&
  currentPwd.value.length > 0 &&
  allChecksPassed.value &&
  confirmOk.value
);

async function submit() {
  if (!canSubmit.value) return;
  submitting.value = true;
  submitError.value = null;
  // КРИТИЧНО: cache forced флаг ДО refresh — иначе после auth.setUser(me)
  // must_change_password станет false и isForced=false, и редирект пойдёт
  // на router.history.state.back (это может быть /login-v2 откуда юзер пришёл).
  const wasForced = isForced.value;
  try {
    await authApi.changePassword(currentPwd.value, newPwd.value);
    // Refresh user state — must_change_password should now be false
    try {
      const me = await authApi.me();
      auth.setUser(me);
    } catch { /* ignore — guard will re-evaluate on next nav */ }
    // Forced flow → home (затем router-guard сам уведёт на mfa-onboarding если нужно).
    // Voluntary → back where they came from.
    await router.replace(wasForced ? "/" : (router.options.history.state?.back as string) || "/");
  } catch (e: any) {
    submitError.value = e?.response?.data?.detail || e?.message || "Не удалось сменить пароль";
  } finally {
    submitting.value = false;
  }
}

const CHECK_LABELS: { key: keyof ReturnType<typeof checks.value.valueOf>; label: string }[] = [
  { key: "length",    label: "Минимум 12 символов" } as any,
  { key: "upper",     label: "Заглавная буква (A-Z)" } as any,
  { key: "lower",     label: "Строчная буква (a-z)" } as any,
  { key: "digit",     label: "Цифра (0-9)" } as any,
  { key: "special",   label: "Спецсимвол (!@#$ …)" } as any,
  { key: "no_repeat", label: "Нет 3+ одинаковых подряд" } as any,
  { key: "no_seq",    label: "Нет последовательностей (1234, qwer)" } as any,
  { key: "no_common", label: "Не в списке распространённых" } as any,
];
</script>

<template>
  <div class="cpw-page">
    <div class="cpw-card">
      <header class="cpw-head">
        <div class="cpw-eyebrow">Безопасность</div>
        <h1 class="cpw-title">{{ isForced ? "Требуется смена пароля" : "Смена пароля" }}</h1>
        <p class="cpw-sub" v-if="isForced">
          Администратор требует обновить ваш пароль либо срок действия пароля истёк.
          Доступ к платформе восстановится сразу после смены.
        </p>
        <p class="cpw-sub" v-else>
          Новый пароль вступит в силу немедленно. Все активные сессии на других устройствах будут завершены.
        </p>
      </header>

      <form class="cpw-form" @submit.prevent="submit">
        <label class="cpw-fld">
          <span class="cpw-fld-lbl">Текущий пароль</span>
          <div class="cpw-input-wrap">
            <input
              :type="showCurrent ? 'text' : 'password'"
              v-model="currentPwd"
              class="cpw-input"
              autocomplete="current-password"
              required
              autofocus
            />
            <button type="button" class="cpw-eye" :aria-label="showCurrent ? 'Скрыть пароль' : 'Показать пароль'" @click="showCurrent = !showCurrent">
              <svg v-if="!showCurrent" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>
              </svg>
              <svg v-else viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/>
              </svg>
            </button>
          </div>
        </label>

        <label class="cpw-fld">
          <span class="cpw-fld-lbl">Новый пароль</span>
          <div class="cpw-input-wrap">
            <input
              :type="showNew ? 'text' : 'password'"
              v-model="newPwd"
              class="cpw-input"
              autocomplete="new-password"
              required
            />
            <button type="button" class="cpw-eye" :aria-label="showNew ? 'Скрыть пароль' : 'Показать пароль'" @click="showNew = !showNew">
              <svg v-if="!showNew" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>
              </svg>
              <svg v-else viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/>
              </svg>
            </button>
          </div>
          <div v-if="newPwd.length > 0" class="cpw-strength">
            <div class="cpw-strength-bar">
              <div class="cpw-strength-fill" :style="{ width: strength + '%', background: strengthColor }"></div>
            </div>
            <span class="cpw-strength-lbl" :style="{ color: strengthColor }">{{ strengthLabel }}</span>
          </div>
        </label>

        <ul class="cpw-checks">
          <li v-for="c in CHECK_LABELS" :key="c.key" :class="{ ok: (checks as any)[c.key] }">
            <span class="cpw-check-icon">{{ (checks as any)[c.key] ? "✓" : "✗" }}</span>
            {{ c.label }}
          </li>
        </ul>

        <label class="cpw-fld">
          <span class="cpw-fld-lbl">Повтор нового пароля</span>
          <div class="cpw-input-wrap">
            <input
              :type="showConfirm ? 'text' : 'password'"
              v-model="confirmPwd"
              class="cpw-input"
              :class="{ 'cpw-input-err': confirmPwd.length > 0 && !confirmOk }"
              autocomplete="new-password"
              required
            />
            <button type="button" class="cpw-eye" :aria-label="showConfirm ? 'Скрыть пароль' : 'Показать пароль'" @click="showConfirm = !showConfirm">
              <svg v-if="!showConfirm" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>
              </svg>
              <svg v-else viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/>
              </svg>
            </button>
          </div>
          <div v-if="confirmPwd.length > 0" class="cpw-confirm-status" :class="{ ok: confirmOk }">
            <span>{{ confirmOk ? "✓ Совпадает" : "✗ Не совпадает" }}</span>
          </div>
        </label>

        <div v-if="submitError" class="cpw-err">{{ submitError }}</div>

        <div class="cpw-actions">
          <button v-if="!isForced" type="button" class="cpw-btn-cancel" @click="router.back()" :disabled="submitting">
            Отмена
          </button>
          <button type="submit" class="cpw-btn-submit" :disabled="!canSubmit">
            {{ submitting ? "Сохраняем…" : "Сменить пароль" }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>

<style scoped>
.cpw-page {
  position: fixed;
  inset: 0;
  width: 100vw;
  height: 100vh;
  /* Унифицированный фон: light girih pattern + linear gradient (как Login) */
  background-color: #F4F2FF;
  background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 96 96' width='96' height='96'><g fill='none' stroke='%23534AB7' stroke-width='0.6' opacity='0.14'><rect x='18' y='18' width='60' height='60'/><rect x='18' y='18' width='60' height='60' transform='rotate(45 48 48)'/><circle cx='48' cy='48' r='10'/><rect x='-12' y='-12' width='24' height='24' transform='rotate(45 0 0)'/><rect x='84' y='-12' width='24' height='24' transform='rotate(45 96 0)'/><rect x='-12' y='84' width='24' height='24' transform='rotate(45 0 96)'/><rect x='84' y='84' width='24' height='24' transform='rotate(45 96 96)'/><line x1='0' y1='48' x2='18' y2='48'/><line x1='78' y1='48' x2='96' y2='48'/><line x1='48' y1='0' x2='48' y2='18'/><line x1='48' y1='78' x2='48' y2='96'/></g></svg>"),
                    linear-gradient(145deg, #EEF0FF 0%, #F4F2FF 40%, #EBF0FF 100%);
  background-repeat: repeat, no-repeat;
  background-attachment: fixed, fixed;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  font-family: -apple-system, system-ui, sans-serif;
  overflow-y: auto;
  z-index: 1;
  box-sizing: border-box;
}
.cpw-card {
  width: 100%;
  max-width: 520px;
  background: rgba(255, 255, 255, 0.65);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid rgba(15, 23, 60, 0.08);
  border-radius: 22px;
  padding: 36px 40px 32px;
  box-shadow:
    0 32px 80px rgba(15, 23, 60, .12),
    0 12px 32px rgba(15, 23, 60, .08);
  margin: auto;
  animation: cpwSlideInRight 0.7s cubic-bezier(0.22, 1, 0.36, 1) both;
}
@supports not ((backdrop-filter: blur(20px)) or (-webkit-backdrop-filter: blur(20px))) {
  .cpw-card { background: rgba(255, 255, 255, 0.92); }
}
@keyframes cpwSlideInRight {
  0%   { opacity: 0; transform: translateX(40px); }
  100% { opacity: 1; transform: translateX(0); }
}
@media (prefers-reduced-motion: reduce) {
  .cpw-card { animation-duration: 0.01s !important; }
}
@media (max-height: 760px) {
  .cpw-page { align-items: flex-start; padding-top: 40px; padding-bottom: 40px; }
}
.cpw-head { margin-bottom: 20px; }
.cpw-eyebrow {
  font-size: 10px;
  font-weight: 500;
  letter-spacing: .08em;
  text-transform: uppercase;
  color: #888780;
}
.cpw-title {
  margin: 4px 0 0 0;
  font-size: 18px;
  font-weight: 500;
  letter-spacing: -.015em;
  color: #1E2A4A;
}
.cpw-sub {
  margin: 6px 0 0 0;
  font-size: 12px;
  color: #888780;
  line-height: 1.45;
}

.cpw-form { display: flex; flex-direction: column; gap: 14px; }
.cpw-fld { display: flex; flex-direction: column; gap: 4px; }
.cpw-fld-lbl {
  font-size: 10px;
  font-weight: 500;
  color: #888780;
  letter-spacing: .06em;
  text-transform: uppercase;
}
.cpw-input-wrap {
  position: relative;
}
.cpw-input {
  width: 100%;
  height: 36px;
  padding: 0 36px 0 10px;
  border: 0.5px solid #E5E7EB;
  border-radius: 7px;
  font-size: 13px;
  font-family: inherit;
  background: #fff;
  color: #1E2A4A;
  outline: none;
  transition: border-color .15s, box-shadow .15s;
}
.cpw-input:focus {
  outline: none;
  border-color: rgba(20, 184, 166, 0.65);
  box-shadow: 0 0 0 3px rgba(20, 184, 166, 0.18);
  background: #ffffff;
}
.cpw-input-err {
  border-color: #E24B4A;
}
/* Спрятать нативный eye-reveal Edge/IE — у нас есть свой .cpw-eye */
.cpw-input::-ms-reveal,
.cpw-input::-ms-clear {
  display: none !important;
}
.cpw-eye {
  position: absolute;
  right: 8px;
  top: 50%;
  transform: translateY(-50%);
  width: 30px;
  height: 30px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  padding: 0;
  color: rgba(15, 23, 60, 0.45);
  transition: color 0.15s, background 0.15s;
}
.cpw-eye:hover { color: rgba(20, 184, 166, 0.9); background: rgba(20, 184, 166, 0.08); }
.cpw-strength {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 6px;
}
.cpw-strength-bar {
  flex: 1;
  height: 4px;
  background: #F1EFE8;
  border-radius: 2px;
  overflow: hidden;
}
.cpw-strength-fill {
  height: 100%;
  transition: width .2s ease, background-color .2s;
}
.cpw-strength-lbl { font-size: 10.5px; font-weight: 500; white-space: nowrap; }

.cpw-checks {
  list-style: none;
  padding: 8px 0 0 0;
  margin: 0;
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 4px 10px;
}
.cpw-checks li {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  color: #888780;
}
.cpw-check-icon {
  width: 16px;
  height: 16px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  font-size: 9px;
  font-weight: 600;
  background: rgba(226, 75, 74, .10);
  color: #C0322F;
}
.cpw-checks li.ok { color: #1E2A4A; }
.cpw-checks li.ok .cpw-check-icon {
  background: rgba(29, 158, 117, .12);
  color: #1D9E75;
}

.cpw-confirm-status {
  font-size: 11px;
  color: #C0322F;
  margin-top: 4px;
}
.cpw-confirm-status.ok { color: #1D9E75; }

.cpw-err {
  padding: 8px 12px;
  background: rgba(226, 75, 74, .06);
  border: 0.5px solid rgba(226, 75, 74, .25);
  border-radius: 7px;
  font-size: 12px;
  color: #C0322F;
}

.cpw-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 6px;
}
.cpw-btn-cancel, .cpw-btn-submit {
  height: 36px;
  padding: 0 18px;
  border-radius: 7px;
  font-size: 12.5px;
  font-family: inherit;
  font-weight: 500;
  cursor: pointer;
}
.cpw-btn-cancel {
  background: transparent;
  border: 0.5px solid #E5E7EB;
  color: #888780;
}
.cpw-btn-submit {
  background: linear-gradient(90deg, #14B8A6 0%, #4F46E5 100%);
  background-size: 200% 100%;
  background-position: 0% 50%;
  color: #fff;
  border: none;
  font-weight: 600;
  letter-spacing: 0.01em;
  transition: background-position 0.4s ease, transform 0.18s cubic-bezier(0.34, 1.2, 0.64, 1), box-shadow 0.18s ease;
  box-shadow: 0 10px 28px rgba(20, 184, 166, 0.18), 0 4px 14px rgba(79, 70, 229, 0.18);
}
.cpw-btn-submit:hover:not(:disabled) {
  background-position: 100% 50%;
  transform: translateY(-1px);
  box-shadow: 0 14px 34px rgba(79, 70, 229, 0.28), 0 6px 18px rgba(20, 184, 166, 0.18);
}
.cpw-btn-submit:disabled { opacity: .5; cursor: not-allowed; }
</style>
