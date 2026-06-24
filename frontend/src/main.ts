import { createApp } from "vue";
import { createPinia } from "pinia";
import App from "./App.vue";
import router from "./router";
import { useAuthStore } from "@/stores/auth";
import { authApi } from "@/api/auth";
import { vCountUp } from "@/utils/countUp";
import { initVersionCheck } from "@/composables/useVersionCheck";

// Chart.js — selective-регистрация ТОЛЬКО используемых контроллеров/шкал/плагинов
// (см. @/utils/chartjsRegister) вместо `...registerables`. Аудит проекта: во всём
// коде используются лишь bar/doughnut/line/radar/bubble — registerables тянул все
// типы и блокировал tree-shaking (charts-чанк раздувался). window.Chart сохранён,
// поэтому legacy-style компоненты (PaTornado, PaRadar,
// MaturityCalendar, RiskTab, LendersTab …) продолжают работать без изменений.
import { Chart } from "@/utils/chartjsRegister";
(window as unknown as { Chart: unknown }).Chart = Chart;

// Self-hosted Geist (canonical UzAssets typeface) — variable wght axis.
// Заменяет внешний Google Fonts CDN (блокировался ERR_CONNECTION_CLOSED).
import "@fontsource-variable/geist/wght.css";
import "@fontsource-variable/geist-mono/wght.css";
import "@/assets/main.css";
import "@/assets/colors_and_type.css";
import "@/assets/uza-kpi-etalon.css";
import "@/assets/uza-top-stripe.css";
import "@/assets/uza-side-stripe.css";
import "@/assets/uza-kit.css";
import "@/assets/elements.css";
import "@/assets/uza-toggles.css";
import "@/assets/uza-premium.css";
import "@/assets/print.css";
import "@/assets/exec-animations.css";
import "@/styles/motion.css";
import "@/assets/responsive.css";  // адаптив крупных дисплеев — импорт последним
import { reveal } from "@/directives/reveal";
import { installNoSpacePasswordGuard } from "@/utils/passwordGuard";

// ─── Stale-chunk recovery after frontend redeploy ─────────────────
// Когда фронт пересобран и появились новые хешированные чанки, у юзера
// в браузере остаётся старый index.js, ссылающийся на удалённые файлы.
// Динамический import() выбрасывает TypeError / ChunkLoadError. Ловим и
// делаем полный reload — браузер подтянет свежий index.html.
function _isChunkLoadError(err: unknown): boolean {
  const e = err as { name?: string; message?: string } | null;
  if (!e) return false;
  const msg = String(e.message || "");
  return (
    e.name === "ChunkLoadError" ||
    msg.includes("Failed to fetch dynamically imported module") ||
    msg.includes("error loading dynamically imported module") ||
    msg.includes("Importing a module script failed") ||
    /Loading (CSS )?chunk \S+ failed/i.test(msg)
  );
}
function _handleStaleChunk(err: unknown): void {
  if (!_isChunkLoadError(err)) return;
  // Guard against reload loop — only reload once per session.
  const key = "__uza_chunk_reload_at";
  const last = Number(sessionStorage.getItem(key) || "0");
  if (Date.now() - last < 30_000) return;
  sessionStorage.setItem(key, String(Date.now()));
   
  console.warn("[uza] Stale chunk detected, reloading…", err);
  window.location.reload();
}
window.addEventListener("error", (e) => _handleStaleChunk(e.error));
window.addEventListener("unhandledrejection", (e) => _handleStaleChunk(e.reason));
// Vite-specific event for preload errors
window.addEventListener("vite:preloadError", (e: Event) => {
  _handleStaleChunk((e as unknown as { payload?: unknown }).payload);
});

const app = createApp(App);
const pinia = createPinia();

app.use(pinia);

// Пароль не может содержать пробел — глобально вырезаем/блокируем пробелы
// во всех input[type=password] (логин, смена/сброс пароля, инвайт, step-up).
installNoSpacePasswordGuard();

// Project-wide standard for animated KPI counters (mirrors legacy _countUpEl).
// Use as: <span v-count-up="940">0</span>
//      or <span v-count-up="{ value: 12.5, decimals: 1, thousandSep: true }">0</span>
app.directive("count-up", vCountUp);
// v-reveal — премиум scroll-reveal (fade-up при входе в вьюпорт, стаггер мс).
app.directive("reveal", reveal);

// On boot: if we have a token, refresh /auth/me so we have the latest
// roles/permissions. If the token is invalid, the response interceptor
// will try refresh; if both fail, bounce to login.
async function bootstrap() {
  const auth = useAuthStore();
  if (auth.accessToken) {
    try {
      const me = await authApi.me();
      auth.setUser(me);
    } catch {
      // Interceptor handles refresh + redirect; we just don't crash here.
    }
  }
  app.use(router);
  app.mount("#app");

  // Cache kill-switch: предлагает обновиться, когда задеплоен новый билд.
  initVersionCheck();
}

void bootstrap();
