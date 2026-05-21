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
  try {
    await authApi.changePassword(currentPwd.value, newPwd.value);
    // Refresh user state — must_change_password should now be false
    try {
      const me = await authApi.me();
      auth.setUser(me);
    } catch { /* ignore — guard will re-evaluate on next nav */ }
    // Forced flow → home. Voluntary → back where they came from.
    await router.replace(isForced.value ? "/" : (router.options.history.state?.back as string) || "/");
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
            <button type="button" class="cpw-eye" @click="showCurrent = !showCurrent" :aria-label="showCurrent ? 'Скрыть' : 'Показать'">
              {{ showCurrent ? "🙈" : "👁" }}
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
            <button type="button" class="cpw-eye" @click="showNew = !showNew">
              {{ showNew ? "🙈" : "👁" }}
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
            <button type="button" class="cpw-eye" @click="showConfirm = !showConfirm">
              {{ showConfirm ? "🙈" : "👁" }}
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
  background: #F4F3F9;
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
  background: #fff;
  border: 0.5px solid #E5E7EB;
  border-radius: 14px;
  padding: 28px 32px;
  box-shadow:
    0 24px 64px rgba(15, 23, 60, .12),
    0 8px 24px rgba(15, 23, 60, .06);
  margin: auto;
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
  border-color: #7F77DD;
  box-shadow: 0 0 0 3px rgba(127, 119, 221, .15);
}
.cpw-input-err {
  border-color: #E24B4A;
}
.cpw-eye {
  position: absolute;
  right: 6px;
  top: 50%;
  transform: translateY(-50%);
  background: transparent;
  border: none;
  cursor: pointer;
  padding: 4px 6px;
  font-size: 14px;
  color: #888780;
}
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
  background: #7F77DD;
  color: #fff;
  border: none;
}
.cpw-btn-submit:hover:not(:disabled) { background: #6B62D6; }
.cpw-btn-submit:disabled { opacity: .5; cursor: not-allowed; }
</style>
