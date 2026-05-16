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
  };
});
