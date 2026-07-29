<script setup lang="ts">
import { computed, ref, onMounted } from "vue";
import { useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { useI18n } from "@/composables/useI18n";

const { t } = useI18n();
const auth = useAuthStore();
const router = useRouter();

const PWD_MAX_AGE_DAYS = 90;
const WARN_WITHIN_DAYS = 7;
const LS_DISMISS_KEY = "uz_pwd_warn_dismissed_v1";

const dismissedFor = ref<string | null>(null);

onMounted(() => {
  try {
    dismissedFor.value = localStorage.getItem(LS_DISMISS_KEY);
  } catch { /* noop */ }
});

const pwdChangedAt = computed<string | null>(() => {
  const u = auth.user as { password_changed_at?: string | null } | null;
  return u?.password_changed_at || null;
});

const daysLeft = computed<number | null>(() => {
  if (!pwdChangedAt.value) return null;
  const ageMs = Date.now() - new Date(pwdChangedAt.value).getTime();
  const ageDays = Math.floor(ageMs / 86400000);
  return PWD_MAX_AGE_DAYS - ageDays;
});

const dismissKey = computed(() => {
  // Key resets daily so the banner re-appears next day
  const today = new Date().toISOString().slice(0, 10);
  return `${pwdChangedAt.value || "none"}|${today}`;
});

const visible = computed(() => {
  if (!auth.isAuthenticated) return false;
  // must_change is handled by router guard — don't double-show banner
  const u = auth.user as { must_change_password?: boolean } | null;
  if (u?.must_change_password) return false;
  const d = daysLeft.value;
  if (d === null) return false;
  if (d > WARN_WITHIN_DAYS) return false;
  if (d < 0) return true; // overdue — never dismissible
  return dismissedFor.value !== dismissKey.value;
});

const severity = computed<"warn" | "crit">(() => {
  const d = daysLeft.value;
  return d !== null && d <= 1 ? "crit" : "warn";
});

const message = computed(() => {
  const d = daysLeft.value;
  if (d === null) return "";
  if (d < 0) return t("Срок пароля истёк {n} дн. назад — смените сейчас, иначе доступ к API будет закрыт.", { n: Math.abs(d) });
  if (d === 0) return t("Срок пароля истекает сегодня — смените прямо сейчас.");
  if (d === 1) return t("Срок пароля истекает завтра — смените сейчас.");
  return t("Срок пароля истекает через {n} дн. — рекомендуем сменить заранее.", { n: d });
});

function goChange() {
  router.push({ name: "change-password" });
}

function dismiss() {
  if ((daysLeft.value ?? 0) < 0) return; // overdue is not dismissible
  dismissedFor.value = dismissKey.value;
  try {
    localStorage.setItem(LS_DISMISS_KEY, dismissKey.value);
  } catch { /* noop */ }
}
</script>

<template>
  <div v-if="visible" :class="['uz-pwd-banner', `uz-pwd-banner-${severity}`]">
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <rect x="3" y="11" width="18" height="11" rx="2" />
      <path d="M7 11V7a5 5 0 0 1 10 0v4" />
    </svg>
    <span class="uz-pwd-banner-msg">{{ message }}</span>
    <button class="uz-pwd-banner-cta" @click="goChange">{{ t("Сменить пароль →") }}</button>
    <button v-if="(daysLeft ?? 0) >= 0" class="uz-pwd-banner-x" :title="t('Скрыть до завтра')" @click="dismiss">✕</button>
  </div>
</template>

<style scoped>
.uz-pwd-banner {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 22px;
  font-size: 12px; font-weight: 500;
  border-bottom: 1px solid;
}
.uz-pwd-banner-warn {
  background: rgba(239,159,39,.10);
  border-bottom-color: rgba(239,159,39,.28);
  color: #854F0B;
}
.uz-pwd-banner-crit {
  background: rgba(226,75,74,.10);
  border-bottom-color: rgba(226,75,74,.30);
  color: #791F1F;
}
.uz-pwd-banner-msg { flex: 1; }
.uz-pwd-banner-cta {
  padding: 4px 10px;
  background: currentColor;
  border: none; border-radius: 6px;
  font-size: 11px; font-weight: 500;
  cursor: pointer; font-family: inherit;
  color: #fff;
}
.uz-pwd-banner-warn .uz-pwd-banner-cta { background: #B27015; }
.uz-pwd-banner-crit .uz-pwd-banner-cta { background: #B81F1E; }
.uz-pwd-banner-cta:hover { filter: brightness(1.1); }
.uz-pwd-banner-x {
  background: transparent; border: none;
  color: currentColor; opacity: .55;
  font-size: 13px; cursor: pointer; font-family: inherit;
  padding: 2px 6px;
}
.uz-pwd-banner-x:hover { opacity: 1; }
</style>
