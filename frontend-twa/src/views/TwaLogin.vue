<script setup lang="ts">
/**
 * TWA bootstrap view (Phase C).
 *
 * Auto-runs login on mount: pulls initData from window.Telegram.WebApp,
 * swaps it for a JWT pair via POST /auth/twa-login, then redirects to
 * the `next` query param (or /twa/ home).
 */
import { onMounted, ref } from "vue";
import { useRouter, useRoute } from "vue-router";
import { useTwaAuth } from "@/composables/useTwaAuth";
import { useTelegramWebApp } from "@/composables/useTelegramWebApp";

const router = useRouter();
const route  = useRoute();
const auth   = useTwaAuth();
const tg     = useTelegramWebApp();

const error = ref<string | null>(null);
const phase = ref<"init" | "auth" | "ok">("init");

async function go() {
  phase.value = "init";
  error.value = null;
  try {
    if (!tg.inside) {
      error.value = "Окно открыто вне Telegram. Откройте бот @UzAssets_bot и нажмите кнопку меню.";
      return;
    }
    phase.value = "auth";
    await auth.ensureLogin();
    phase.value = "ok";
    const next = (route.query.next as string) || "/twa/";
    router.replace(next);
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || "Не удалось войти";
    tg.haptics?.notificationOccurred("error");
  }
}

onMounted(go);
</script>

<template>
  <main class="flex flex-col items-center justify-center min-h-screen p-6 gap-4 text-center">
    <div v-if="phase !== 'ok' && !error" class="flex flex-col items-center gap-3">
      <div class="twa-spinner"></div>
      <div class="text-tg-hint text-sm">
        {{ phase === "auth" ? "Авторизация через Telegram…" : "Подготовка…" }}
      </div>
    </div>

    <div v-if="error" class="flex flex-col items-center gap-4 max-w-sm">
      <div class="w-12 h-12 rounded-full bg-uza-red/15 text-uza-red flex items-center justify-center text-2xl">!</div>
      <div class="font-medium text-base">Ошибка входа</div>
      <p class="text-sm text-tg-hint">{{ error }}</p>
      <button
        @click="go"
        class="px-5 py-2 rounded-card bg-tg-button text-tg-button-text text-sm font-medium hover:opacity-90 transition"
      >Повторить</button>
    </div>
  </main>
</template>

<style scoped>
.twa-spinner {
  width: 36px; height: 36px;
  border: 3px solid rgba(127, 119, 221, 0.18);
  border-top-color: var(--tg-theme-button-color, #7F77DD);
  border-radius: 50%;
  animation: twaSpin .8s linear infinite;
}
@keyframes twaSpin { to { transform: rotate(360deg); } }
</style>
