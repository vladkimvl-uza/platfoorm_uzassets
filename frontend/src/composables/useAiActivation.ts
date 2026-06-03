// useAiActivation — глобальное состояние активации ИИ-ассистента (singleton).
//
// Owner может включать/выключать ассистента; флаг хранится на бэке
// (GET/PUT /ai/activation). Все места UI (карточка в сайдбаре, заголовок
// AiChat «онлайн/выключен», тумблер в AiSidebar) читают ОДНО состояние,
// поэтому переключение мгновенно отражается везде.
import { reactive } from "vue";
import { api } from "@/api/client";

const state = reactive({
  active: true,
  canToggle: false,
  loaded: false,
});

let inflight: Promise<void> | null = null;

async function load(force = false): Promise<void> {
  if (state.loaded && !force) return;
  if (inflight) return inflight;
  inflight = (async () => {
    try {
      const { data } = await api.get("/ai/activation");
      state.active = !!data.active;
      state.canToggle = !!data.can_toggle;
      state.loaded = true;
    } catch { /* ignore — оставляем дефолт active=true */ }
    finally { inflight = null; }
  })();
  return inflight;
}

async function setActive(v: boolean): Promise<void> {
  try {
    const { data } = await api.put("/ai/activation", { active: v });
    state.active = !!data.active;
  } catch { /* ignore */ }
}

export function useAiActivation() {
  return {
    state,
    load,
    setActive,
    toggle: () => setActive(!state.active),
  };
}
