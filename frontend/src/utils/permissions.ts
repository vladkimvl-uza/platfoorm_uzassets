/**
 * utils/permissions.ts
 * ─────────────────────────────────────────────────────────────────
 * Единая точка истины для проверок прав в UI.
 *
 * Использование:
 *   import { useCanEdit } from "@/utils/permissions";
 *   const canEdit = useCanEdit();           // → ComputedRef<boolean>
 *
 *   <EditableField :editable="canEdit" ... />
 *
 * Гейт: is_owner OR has_permission("companies.edit") OR role "admin".
 * Совпадает с бэкендом app/api/routes/companies.py update_company().
 *
 * Pack 7.29: добавлено для CompanyDrillModal; рассчитано на переиспользование
 * во всех будущих модалках где админ редактирует company-scope данные.
 */
import { computed, type ComputedRef } from "vue";
import { useAuthStore } from "@/stores/auth";

/** Может ли текущий пользователь редактировать данные компании. */
export function useCanEdit(): ComputedRef<boolean> {
  const auth = useAuthStore();
  return computed(() =>
    auth.isOwner ||
    auth.hasPermission("companies.edit") ||
    auth.hasRole("admin"),
  );
}

/** Может ли текущий пользователь редактировать конкретный permission code. */
export function useHasPermission(code: string): ComputedRef<boolean> {
  const auth = useAuthStore();
  return computed(() => auth.isOwner || auth.hasPermission(code));
}
