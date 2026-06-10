/**
 * usePermissions — central permission resolver for hide-on-no-access pattern.
 *
 * Reads from auth store: user.permissions[] + user.module_visibility + roles[].
 * Returns reactive booleans for each action in a given module.
 *
 * USAGE:
 *   <script setup>
 *   import { usePermissions } from '@/composables/usePermissions';
 *   const perm = usePermissions('kpi');
 *   </script>
 *
 *   <template>
 *     <button v-if="perm.canEdit">Edit</button>
 *     <button v-if="perm.canExport">Export</button>
 *   </template>
 *
 * The "level" property gives a coarse 4-value (none / read / write / admin)
 * derived from the most permissive action available. Used by Access-карта
 * to show one chip per module.
 */
import { computed } from 'vue';
import { useAuthStore } from '@/stores/auth';

export type AccessLevel = 'none' | 'read' | 'write' | 'admin';

export interface PermissionResult {
  level: AccessLevel;
  canView: boolean;
  canEdit: boolean;
  canApprove: boolean;
  canExport: boolean;
  canDelete: boolean;
  canManage: boolean;
  explain: string;
}

function _hasCode(codes: string[], moduleCode: string, action: string): boolean {
  return codes.includes(`${moduleCode}.${action}`) ||
         codes.includes(`${moduleCode}.manage`) ||
         codes.includes('*');
}

function _computeLevel(r: { canView: boolean; canEdit: boolean; canManage: boolean }): AccessLevel {
  if (r.canManage) return 'admin';
  if (r.canEdit) return 'write';
  if (r.canView) return 'read';
  return 'none';
}

export function usePermissions(moduleCode: string) {
  const auth = useAuthStore();

  const result = computed<PermissionResult>(() => {
    const user = auth.user;
    if (!user) {
      return {
        level: 'none', canView: false, canEdit: false, canApprove: false,
        canExport: false, canDelete: false, canManage: false,
        explain: 'не авторизован',
      };
    }
    // Owner bypass — full access everywhere
    if (user.is_owner) {
      return {
        level: 'admin', canView: true, canEdit: true, canApprove: true,
        canExport: true, canDelete: true, canManage: true,
        explain: 'владелец платформы',
      };
    }
    // Extract permission codes from user.permissions (direct grants)
    const perms = (user.permissions || []) as Array<string | { code: string; is_denied?: boolean }>;
    const grantedCodes: string[] = [];
    const deniedCodes: string[] = [];
    const codeSource: Record<string, string> = {}; // code -> origin
    for (const p of perms) {
      if (typeof p === 'string') {
        grantedCodes.push(p);
        codeSource[p] = codeSource[p] || 'manual grant';
      } else if (p && typeof p === 'object') {
        if (p.is_denied) deniedCodes.push(p.code);
        else {
          grantedCodes.push(p.code);
          codeSource[p.code] = codeSource[p.code] || 'manual grant';
        }
      }
    }
    // Pack 141b: group-derived permissions
    const groups = (user.groups || []) as Array<{ code?: string; name?: string; permissions?: Array<string | { code: string }> }>;
    for (const g of groups) {
      const gName = g.name || g.code || 'group';
      for (const gp of (g.permissions || [])) {
        const code = typeof gp === 'string' ? gp : gp?.code;
        if (!code) continue;
        if (!grantedCodes.includes(code)) grantedCodes.push(code);
        if (!codeSource[code]) codeSource[code] = `via group: ${gName}`;
      }
    }
    // Module visibility: if explicitly hidden, return 'none' regardless of permissions
    const mv = (user.module_visibility || {}) as Record<string, boolean>;
    if (mv[moduleCode] === false) {
      return {
        level: 'none', canView: false, canEdit: false, canApprove: false,
        canExport: false, canDelete: false, canManage: false,
        explain: 'модуль скрыт администратором',
      };
    }
    // Role-based bypass: admin / ceo roles get admin level on everything
    const roleCodes = (user.roles || []).map((r: any) =>
      typeof r === 'string' ? r : r.code
    );
    if (roleCodes.includes('admin') || roleCodes.includes('ceo')) {
      return {
        level: 'admin', canView: true, canEdit: true, canApprove: true,
        canExport: true, canDelete: true, canManage: true,
        explain: `via role: ${roleCodes.includes('admin') ? 'admin' : 'ceo'}`,
      };
    }
    // Compute per-action booleans
    const isDenied = (action: string) =>
      deniedCodes.includes(`${moduleCode}.${action}`);
    const canView    = !isDenied('view')   && _hasCode(grantedCodes, moduleCode, 'view');
    const canEdit    = !isDenied('edit')   && _hasCode(grantedCodes, moduleCode, 'edit');
    const canApprove = !isDenied('approve')&& _hasCode(grantedCodes, moduleCode, 'approve');
    const canExport  = !isDenied('export') && _hasCode(grantedCodes, moduleCode, 'export');
    const canDelete  = !isDenied('delete') && _hasCode(grantedCodes, moduleCode, 'delete');
    const canManage  = !isDenied('manage') && grantedCodes.includes(`${moduleCode}.manage`);
    const level = _computeLevel({ canView, canEdit, canManage });
    return {
      level, canView, canEdit, canApprove, canExport, canDelete, canManage,
      explain: level === 'none' ? 'нет в роли' : `via permissions`,
    };
  });

  return {
    level:      computed(() => result.value.level),
    canView:    computed(() => result.value.canView),
    canEdit:    computed(() => result.value.canEdit),
    canApprove: computed(() => result.value.canApprove),
    canExport:  computed(() => result.value.canExport),
    canDelete:  computed(() => result.value.canDelete),
    canManage:  computed(() => result.value.canManage),
    explain:    computed(() => result.value.explain),
  };
}

/**
 * MODULE_REGISTRY — single source of truth for the 16 modules used
 * across RBAC v3 Access-карта and Roles editor.
 */
export const MODULE_REGISTRY = [
  { code: 'dashboard',    label: 'Дашборд'           },
  { code: 'bp',           label: 'Бизнес-план'       },
  { code: 'kpi',          label: 'KPI'               },
  { code: 'financials',   label: 'Финансы (МСФО/НСБУ)' },
  { code: 'credit',       label: 'Кредитный портфель' },
  { code: 'invest',       label: 'Инвест-проекты'    },
  { code: 'procurement',  label: 'Закупки'           },
  { code: 'esg',          label: 'ESG'               },
  { code: 'governance',   label: 'Корпуправление'    },
  { code: 'ratings',      label: 'Рейтинги'          },
  { code: 'procurement_analysis', label: 'Анализ закупок' },
  { code: 'consultants',  label: 'Консультанты'      },
  { code: 'tasks',        label: 'Задачи'            },
  { code: 'reports',      label: 'Отчёты'            },
  { code: 'monitoring',   label: 'Мониторинг (Execution Summary)' },
  { code: 'ai',           label: 'AI-чат'            },
  { code: 'admin',        label: 'Администрирование' },
] as const;

export type ModuleCode = typeof MODULE_REGISTRY[number]['code'];