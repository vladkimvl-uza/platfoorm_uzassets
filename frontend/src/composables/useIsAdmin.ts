/**
 * useIsAdmin — единое определение «админ ли текущий пользователь».
 *
 * Раньше эта проверка была inline-дублирована в SystemConfig.vue,
 * ScenariosTab.vue, CreditNagruzkaTab.vue, ElasticityProjectsTab.vue.
 * Если меняются роли / схема пользователей — менять надо было в 4 местах.
 *
 * Правило:
 *   admin = user.is_owner OR user.is_admin OR
 *           role in ("admin", "ROLE_ADMIN", "ROLE_OWNER")
 *
 * Возвращает reactive computed<boolean>.
 */
import { computed, type ComputedRef } from "vue";
import { useAuthStore } from "@/stores/auth";

const ADMIN_ROLE_NAMES = new Set(["admin", "ROLE_ADMIN", "ROLE_OWNER"]);

export function useIsAdmin(): ComputedRef<boolean> {
  const auth = useAuthStore();
  return computed<boolean>(() => {
    const u = auth.user as any;
    if (!u) return false;
    if (u.is_owner === true || u.is_admin === true) return true;
    const roles: string[] = Array.isArray(u.roles) ? u.roles : [];
    return roles.some((r) => ADMIN_ROLE_NAMES.has(r));
  });
}
