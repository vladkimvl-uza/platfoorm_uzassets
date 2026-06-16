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
  // Режим доступа: "owner_only" (по умолчанию) | "rbac". hasAccess — есть ли
  // доступ у ТЕКУЩЕГО пользователя (с учётом режима). Используется, чтобы
  // показывать «серый» неактивный ассистент тем, у кого доступа нет.
  accessMode: "owner_only" as "owner_only" | "rbac",
  hasAccess: false,
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
      state.accessMode = data.access_mode === "rbac" ? "rbac" : "owner_only";
      state.hasAccess = !!data.has_access;
      state.loaded = true;
    } catch { /* ignore — оставляем дефолт */ }
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

async function setAccessMode(mode: "owner_only" | "rbac"): Promise<void> {
  try {
    const { data } = await api.put("/ai/access-mode", { mode });
    state.accessMode = data.access_mode === "rbac" ? "rbac" : "owner_only";
    await load(true);
  } catch { /* ignore */ }
}

export function useAiActivation() {
  return {
    state,
    load,
    setActive,
    setAccessMode,
    toggle: () => setActive(!state.active),
  };
}
