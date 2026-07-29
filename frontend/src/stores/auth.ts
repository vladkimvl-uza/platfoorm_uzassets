import { defineStore } from "pinia";
import { ref, computed } from "vue";
import type { TokenPair, User } from "@/api/auth";

export const useAuthStore = defineStore("auth", () => {
  // --- State ---
  const accessToken  = ref<string | null>(localStorage.getItem("uza_access_token"));
  const refreshToken = ref<string | null>(localStorage.getItem("uza_refresh_token"));
  const user         = ref<User | null>(JSON.parse(localStorage.getItem("uza_user") || "null"));

  // --- Getters ---
  const isAuthenticated = computed(() => !!accessToken.value && !!user.value);
  const isOwner         = computed(() => user.value?.is_owner === true);
  const userRoles       = computed(() => user.value?.roles ?? []);
  const userPermissions = computed(() => user.value?.permissions ?? []);

  // --- Mutations ---
  function setTokens(tokens: TokenPair) {
    accessToken.value  = tokens.access_token;
    refreshToken.value = tokens.refresh_token;
    localStorage.setItem("uza_access_token",  tokens.access_token);
    localStorage.setItem("uza_refresh_token", tokens.refresh_token);
  }

  function setUser(u: User) {
    user.value = u;
    localStorage.setItem("uza_user", JSON.stringify(u));
    // Язык из профиля применяем, только если на устройстве язык ещё не
    // выбирали (локальный выбор сильнее профиля); sync=false — без эха.
    try {
      const uiLoc = (u as unknown as { ui_locale?: string }).ui_locale;
      if (uiLoc && !localStorage.getItem("uza-locale-v1")) {
        void import("@/stores/locale").then(({ useLocaleStore }) => {
          const st = useLocaleStore();
          st.set(uiLoc as never, { sync: false });
        });
      }
    } catch { /* приватный режим */ }
  }

  function clear() {
    accessToken.value  = null;
    refreshToken.value = null;
    user.value         = null;
    localStorage.removeItem("uza_access_token");
    localStorage.removeItem("uza_refresh_token");
    localStorage.removeItem("uza_user");
  }

  // --- RBAC helpers ---
  function hasPermission(code: string): boolean {
    if (isOwner.value) return true;
    if (userRoles.value.includes("admin")) return true;
    return userPermissions.value.includes(code);
  }

  function hasRole(...codes: string[]): boolean {
    if (isOwner.value) return true;
    return codes.some((c) => userRoles.value.includes(c));
  }

  // Default landing route after login (call AFTER setUser).
  // Per user request 2026-05-23: всех у кого есть доступ к
  // executive-dashboard кидаем туда; остальные — на корень (тот разрулит роутер).
  // Право проверяем то же, что гейт маршрута (exec_dashboard.view): иначе
  // носитель одних только Финансов улетал бы на экран, откуда гейт сразу
  // выбрасывает на /dashboard с ?denied=.
  function defaultLanding(): string {
    return hasPermission("exec_dashboard.view") ? "/executive-dashboard" : "/";
  }

  return {
    accessToken,
    refreshToken,
    user,
    isAuthenticated,
    isOwner,
    userRoles,
    userPermissions,
    setTokens,
    setUser,
    clear,
    hasPermission,
    hasRole,
    defaultLanding,
  };
});
