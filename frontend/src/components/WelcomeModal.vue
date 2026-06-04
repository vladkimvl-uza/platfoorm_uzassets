<script setup lang="ts">
/**
 * WelcomeModal — приветственное окно первого входа.
 *
 * Показывается один раз (флаг user.welcome_seen на бэке). Premium-оформление
 * с анимациями: приветствие + просьба заполнить данные профиля. Сохранение
 * через PATCH /auth/me, закрытие помечает welcome_seen.
 */
import { ref, computed, onMounted } from "vue";
import { authApi, type User } from "@/api/auth";
import { useAuthStore } from "@/stores/auth";

const emit = defineEmits<{ (e: "close"): void }>();
const auth = useAuthStore();

const fullName   = ref(auth.user?.full_name || "");
const jobTitle   = ref((auth.user as any)?.job_title || "");
const department = ref(auth.user?.department || "");
const phone      = ref(auth.user?.phone || "");

const saving = ref(false);
const error  = ref("");
const mounted = ref(false);
onMounted(() => { requestAnimationFrame(() => (mounted.value = true)); });

const firstName = computed(() => {
  const n = (auth.user?.full_name || "").trim();
  if (n) return n.split(/\s+/)[0];
  const e = auth.user?.email || "";
  return e.split("@")[0] || "коллега";
});

const initials = computed(() => {
  const n = (auth.user?.full_name || auth.user?.email || "?").trim();
  const parts = n.split(/\s+/).filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return (parts[0]?.slice(0, 2) || "?").toUpperCase();
});

async function finish(save: boolean) {
  if (saving.value) return;
  saving.value = true;
  error.value = "";
  try {
    if (save) {
      const updated: User = await authApi.updateMe({
        full_name: fullName.value.trim() || undefined,
        job_title: jobTitle.value.trim() || undefined,
        department: department.value.trim() || undefined,
        phone: phone.value.trim() || undefined,
      });
      auth.setUser({ ...updated, welcome_seen: true });
    } else if (auth.user) {
      auth.setUser({ ...auth.user, welcome_seen: true });
    }
    try { await authApi.dismissWelcome(); } catch { /* best-effort */ }
    close();
  } catch (e: any) {
    error.value = e?.response?.data?.detail || "Не удалось сохранить профиль";
  } finally {
    saving.value = false;
  }
}

function close() {
  mounted.value = false;
  setTimeout(() => emit("close"), 180);
}
</script>

<template>
  <div class="wlc-overlay" :class="{ in: mounted }">
    <div class="wlc-card" :class="{ in: mounted }">
      <!-- Брендовая шапка с градиентом -->
      <div class="wlc-hero">
        <div class="wlc-hero-glow" />
        <div class="wlc-avatar">{{ initials }}</div>
        <div class="wlc-eyebrow">UzAssets · Единая платформа трансформации</div>
        <div class="wlc-title">Добро пожаловать, {{ firstName }}</div>
        <div class="wlc-sub">Рады видеть вас на платформе. Давайте заполним профиль —
          это займёт меньше минуты и поможет коллегам узнавать вас.</div>
      </div>

      <!-- Форма профиля -->
      <div class="wlc-body">
        <div class="wlc-field" style="--d: 0ms">
          <label>ФИО</label>
          <input v-model="fullName" type="text" placeholder="Фамилия Имя Отчество" />
        </div>
        <div class="wlc-row">
          <div class="wlc-field" style="--d: 60ms">
            <label>Должность</label>
            <input v-model="jobTitle" type="text" placeholder="напр. Финансовый аналитик" />
          </div>
          <div class="wlc-field" style="--d: 120ms">
            <label>Отдел</label>
            <input v-model="department" type="text" placeholder="напр. Финансовый блок" />
          </div>
        </div>
        <div class="wlc-field" style="--d: 180ms">
          <label>Телефон</label>
          <input v-model="phone" type="tel" placeholder="+998 ..." />
        </div>

        <div v-if="error" class="wlc-error">{{ error }}</div>

        <div class="wlc-actions">
          <button class="wlc-btn-ghost" :disabled="saving" @click="finish(false)">
            Заполнить позже
          </button>
          <button class="wlc-btn-primary" :disabled="saving" @click="finish(true)">
            {{ saving ? "Сохраняю…" : "Сохранить и продолжить" }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.wlc-overlay {
  position: fixed; inset: 0; z-index: 80;
  display: flex; align-items: center; justify-content: center; padding: 20px;
  background: rgba(15, 18, 40, 0); backdrop-filter: blur(0px);
  transition: background .3s ease, backdrop-filter .3s ease;
}
.wlc-overlay.in { background: rgba(15, 18, 40, .5); backdrop-filter: blur(8px); }

.wlc-card {
  width: 100%; max-width: 480px;
  background: #fff; border-radius: 18px; overflow: hidden;
  box-shadow: 0 30px 80px rgba(15, 23, 60, .28), 0 10px 28px rgba(15, 23, 60, .12);
  opacity: 0; transform: translateY(22px) scale(.95);
  transition: opacity .42s cubic-bezier(.34, 1.2, .64, 1),
              transform .42s cubic-bezier(.34, 1.2, .64, 1);
}
.wlc-card.in { opacity: 1; transform: translateY(0) scale(1); }

/* Hero */
.wlc-hero {
  position: relative; overflow: hidden;
  padding: 30px 28px 26px;
  background: linear-gradient(135deg, #1E2A4A 0%, #534AB7 70%, #7F77DD 100%);
  color: #fff; text-align: center;
}
.wlc-hero-glow {
  position: absolute; top: -60px; right: -40px;
  width: 220px; height: 220px; border-radius: 50%;
  background: radial-gradient(circle, rgba(127,119,221,.55), transparent 70%);
  animation: wlcGlow 6s ease-in-out infinite alternate;
}
@keyframes wlcGlow {
  0% { transform: translate(0, 0) scale(1); opacity: .8; }
  100% { transform: translate(-16px, 14px) scale(1.15); opacity: 1; }
}
.wlc-avatar {
  position: relative;
  width: 60px; height: 60px; margin: 0 auto 14px;
  border-radius: 16px;
  display: flex; align-items: center; justify-content: center;
  font-size: 22px; font-weight: 500; letter-spacing: .02em;
  background: rgba(255, 255, 255, .16);
  border: 1px solid rgba(255, 255, 255, .28);
  backdrop-filter: blur(4px);
  animation: wlcPop .5s cubic-bezier(.34, 1.4, .64, 1) .12s both;
}
@keyframes wlcPop {
  0% { opacity: 0; transform: scale(.5) rotate(-8deg); }
  100% { opacity: 1; transform: scale(1) rotate(0); }
}
.wlc-eyebrow {
  position: relative;
  font-size: 10px; font-weight: 500; letter-spacing: .08em; text-transform: uppercase;
  color: rgba(255, 255, 255, .7);
}
.wlc-title {
  position: relative;
  font-size: 21px; font-weight: 500; letter-spacing: -.02em; margin-top: 6px;
}
.wlc-sub {
  position: relative;
  font-size: 12.5px; line-height: 1.55; color: rgba(255, 255, 255, .8);
  margin-top: 8px; max-width: 380px; margin-left: auto; margin-right: auto;
}

/* Body */
.wlc-body { padding: 22px 26px 24px; }
.wlc-row { display: flex; gap: 12px; }
.wlc-row .wlc-field { flex: 1; }
.wlc-field {
  margin-bottom: 13px;
  opacity: 0; transform: translateY(8px);
  animation: wlcField .4s cubic-bezier(.34, 1.2, .64, 1) forwards;
  animation-delay: var(--d, 0ms);
}
@keyframes wlcField { to { opacity: 1; transform: translateY(0); } }
.wlc-field label {
  display: block; font-size: 11px; font-weight: 500; color: #888780;
  margin-bottom: 5px; letter-spacing: .02em;
}
.wlc-field input {
  width: 100%; box-sizing: border-box;
  padding: 9px 12px; font-size: 13px; font-family: inherit; color: #1E2A4A;
  border: 1px solid #E5E7EB; border-radius: 9px; outline: none;
  transition: border-color .14s, box-shadow .14s;
}
.wlc-field input:focus { border-color: #7F77DD; box-shadow: 0 0 0 3px rgba(127, 119, 221, .15); }
.wlc-field input::placeholder { color: #C9C8C0; }

.wlc-error {
  font-size: 12px; color: #E24B4A; margin: 2px 0 10px;
  background: rgba(226, 75, 74, .07); padding: 8px 11px; border-radius: 8px;
}

.wlc-actions { display: flex; gap: 10px; margin-top: 18px; }
.wlc-btn-ghost, .wlc-btn-primary {
  padding: 11px 16px; border-radius: 10px; font-size: 13px; font-weight: 500;
  cursor: pointer; font-family: inherit; transition: background .14s, border-color .14s, box-shadow .14s;
}
.wlc-btn-ghost {
  flex: 0 0 auto;
  border: 1px solid #E5E7EB; background: #fff; color: #888780;
}
.wlc-btn-ghost:hover { background: #FAFAFC; color: #534AB7; border-color: #7F77DD; }
.wlc-btn-primary {
  flex: 1;
  border: 1px solid #7F77DD;
  background: linear-gradient(135deg, #7F77DD, #534AB7); color: #fff;
  box-shadow: 0 4px 14px rgba(127, 119, 221, .3);
}
.wlc-btn-primary:hover { box-shadow: 0 6px 20px rgba(127, 119, 221, .42); }
.wlc-btn-ghost:disabled, .wlc-btn-primary:disabled { opacity: .55; cursor: not-allowed; }
</style>
