// useAiActivation — глобальное состояние активации ИИ-ассистента (singleton).
//
// Owner может включать/выключать ассистента; флаг хранится на бэке
// (GET/PUT /ai/activation). Все места UI (карточка в сайдбаре, заголовок
// AiChat «онлайн/выключен», тумблер в AiSidebar) читают ОДНО состояние,
// поэтому переключение мгновенно отражается везде.
import { reactive } from "vue";
import { api } from "@/api/client";
import { useToast } from "@/composables/useToast";

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

function _reason(e: any): string {
  return e?.response?.data?.detail || e?.message || "неизвестная ошибка";
}

// P1 аудита: обе операции глушили ошибку молча (`catch { /* ignore */ }`).
// Владелец тянул тумблер «выключить ассистента для организации», запрос падал
// (сеть/502/истёкший токен), тумблер отпружинивал — и человек оставался в
// уверенности, что ИИ выключен, хотя он работал. Канон платформы: никаких
// тихих провалов — явный тост «не сохранено» с причиной.
async function setActive(v: boolean): Promise<void> {
  try {
    const { data } = await api.put("/ai/activation", { active: v });
    state.active = !!data.active;
    useToast().success(state.active ? "ИИ-ассистент включён" : "ИИ-ассистент выключен");
  } catch (e) {
    useToast().error(`Не удалось изменить состояние ассистента: ${_reason(e)}`);
    await load(true);   // вернуть UI к РЕАЛЬНОМУ состоянию сервера
  }
}

async function setAccessMode(mode: "owner_only" | "rbac"): Promise<void> {
  try {
    const { data } = await api.put("/ai/access-mode", { mode });
    state.accessMode = data.access_mode === "rbac" ? "rbac" : "owner_only";
    await load(true);
    useToast().success(
      state.accessMode === "rbac"
        ? "Доступ к ИИ: по правам (ai.view)"
        : "Доступ к ИИ: только владелец",
    );
  } catch (e) {
    useToast().error(`Не удалось изменить режим доступа: ${_reason(e)}`);
    await load(true);
  }
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
