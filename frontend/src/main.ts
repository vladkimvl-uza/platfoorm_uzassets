import { createApp } from "vue";
import { createPinia } from "pinia";
import App from "./App.vue";
import router from "./router";
import { useAuthStore } from "@/stores/auth";
import { authApi } from "@/api/auth";
import { vCountUp } from "@/utils/countUp";
import { initTheme } from "@/composables/useTheme";
import ThemeToggle from "@/components/ThemeToggle.vue";

// style components can reference `window.Chart` (e.g. SignatureDonut, DonutCard,
// PaTornado, PaRadar, MaturityCalendar, RiskTab, OverviewSingleCompany, LendersTab).
// surface it the same way after npm registration so existing code Just Works.
import { Chart, registerables } from "chart.js";
Chart.register(...registerables);
(window as unknown as { Chart: unknown }).Chart = Chart;

import "@/assets/main.css";
import "@/assets/uza-kpi-etalon.css";
import "@/assets/uza-top-stripe.css";
import "@/assets/uza-side-stripe.css";
import "@/assets/uza-theme-dark.css";
import "@/assets/uza-kit.css";
import "@/assets/elements.css";
import "@/assets/exec-animations.css";
import "@/styles/motion.css";

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
  // eslint-disable-next-line no-console
  console.warn("[uza] Stale chunk detected, reloading…", err);
  window.location.reload();
}
window.addEventListener("error", (e) => _handleStaleChunk(e.error));
window.addEventListener("unhandledrejection", (e) => _handleStaleChunk(e.reason));
// Vite-specific event for preload errors
window.addEventListener("vite:preloadError", (e: Event) => {
  _handleStaleChunk((e as unknown as { payload?: unknown }).payload);
});

// D12 — применяем сохранённую тему до маунта (без вспышки светлой темы)
initTheme();

const app = createApp(App);
const pinia = createPinia();

app.use(pinia);

// Use as: <span v-count-up="940">0</span>
//      or <span v-count-up="{ value: 12.5, decimals: 1, thousandSep: true }">0</span>
app.directive("count-up", vCountUp);

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

  // Плавающий переключатель темы — отдельный mount в body, не трогаем AppShell
  const themeMount = document.createElement("div");
  document.body.appendChild(themeMount);
  createApp(ThemeToggle).mount(themeMount);
}

void bootstrap();
