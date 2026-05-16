import { createApp } from "vue";
import { createPinia } from "pinia";
import App from "./App.vue";
import router from "./router";
import { useAuthStore } from "@/stores/auth";
import { authApi } from "@/api/auth";
import { vCountUp } from "@/utils/countUp";

// style components can reference `window.Chart` (e.g. SignatureDonut, DonutCard,
// PaTornado, PaRadar, MaturityCalendar, RiskTab, OverviewSingleCompany, LendersTab).
// surface it the same way after npm registration so existing code Just Works.
import { Chart, registerables } from "chart.js";
Chart.register(...registerables);
(window as unknown as { Chart: unknown }).Chart = Chart;

import "@/assets/main.css";
import "@/assets/uza-kpi-etalon.css";
import "@/assets/exec-animations.css";
import "@/styles/motion.css";

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
}

void bootstrap();
