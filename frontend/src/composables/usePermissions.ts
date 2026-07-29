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
 * The "level" property gives a coarse 3-value (none / read / write) derived
 * from the most permissive action available. Used by Access-карта, чтобы
 * показать один чип на модуль.
 *
 * Почему уровней три, а не четыре: уровень «admin» (право {module}.manage)
 * — это профиль РОЛИ, а не персональная надстройка. Через него шла
 * эскалация (выбор «admin» в сетке выдавал manage-права), поэтому из
 * пользовательского выбора он убран. Право manage, выданное ролью,
 * по-прежнему читается ниже как canManage и подразумевает edit/view.
 */
import { computed } from 'vue';
import { useAuthStore } from '@/stores/auth';

export type AccessLevel = 'none' | 'read' | 'write';

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

const PERMISSION_ALIASES: Record<string, string[]> = {
  'ai.view': ['ai.chat'],
  'ai.edit': ['ai.view'],
  'ai.export': ['ai.view'],
  'ai.manage': ['ai.manage', 'ai.admin'],
  'admin.view': ['admin.users'],
  'admin.edit': ['admin.users'],
  'admin.export': ['admin.users'],
  'admin.manage': ['admin.users'],
};

const MODULE_CODE_ALIASES: Record<string, string> = {
  invest: 'investment',
};

function _candidateCodes(moduleCode: string, action: string): string[] {
  const canonicalCode = MODULE_CODE_ALIASES[moduleCode] || moduleCode;
  const code = `${canonicalCode}.${action}`;
  return [code, ...(PERMISSION_ALIASES[code] || [])];
}

function _hasCode(codes: string[], moduleCode: string, action: string): boolean {
  return _candidateCodes(moduleCode, action).some(c => codes.includes(c)) ||
         _candidateCodes(moduleCode, 'manage').some(c => codes.includes(c)) ||
         codes.includes('*');
}

// Уровень «admin» из шкалы убран: manage-право уже подразумевает edit
// (см. _hasCode), поэтому носитель manage получает 'write' — самый высокий
// уровень, который умеет выдавать сетка доступа.
function _computeLevel(r: { canView: boolean; canEdit: boolean }): AccessLevel {
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
        level: 'write', canView: true, canEdit: true, canApprove: true,
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
    // group-derived permissions
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
    // Role-based bypass: mirrors backend is_super_admin.
    const roleCodes = (user.roles || []).map((r: any) =>
      typeof r === 'string' ? r : r.code
    );
    if (roleCodes.includes('admin')) {
      return {
        level: 'write', canView: true, canEdit: true, canApprove: true,
        canExport: true, canDelete: true, canManage: true,
        explain: 'via role: admin',
      };
    }
    // Compute per-action booleans
    const isDenied = (action: string) =>
      _candidateCodes(moduleCode, action).some(c => deniedCodes.includes(c));
    const canView    = !isDenied('view')   && _hasCode(grantedCodes, moduleCode, 'view');
    const canEdit    = !isDenied('edit')   && _hasCode(grantedCodes, moduleCode, 'edit');
    const canApprove = !isDenied('approve')&& _hasCode(grantedCodes, moduleCode, 'approve');
    const canExport  = !isDenied('export') && _hasCode(grantedCodes, moduleCode, 'export');
    const canDelete  = !isDenied('delete') && _hasCode(grantedCodes, moduleCode, 'delete');
    const canManage  = !isDenied('manage') && _hasCode(grantedCodes, moduleCode, 'manage');
    const level = _computeLevel({ canView, canEdit });
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
 * MODULE_REGISTRY — single source of truth for modules used
 * across RBAC v3 Access-карта and Roles editor.
 *
 * Флаги hasExport / hasEdit / hasImport описывают, какие коды РЕАЛЬНО есть в
 * каталоге прав (сверено с каталогом прода). Это не украшение: бэкенд молча
 * отбрасывает несуществующие коды (`desired = {c for c in payload if c in valid}`),
 * поэтому выбор уровня, за которым нет кода, не сохранялся бы вообще. Модули
 * без hasEdit/hasImport (ai, reports, exec_dashboard, exec_overview) не могут
 * получить уровень «Редактировать» — в сетке он для них недоступен: за этими
 * экранами нет ни одного пишущего эндпоинта, и уровень был бы обманом.
 *
 * Модуль «Администрирование» намеренно ОТСУТСТВУЕТ: это управление платформой
 * (admin.users даёт создание пользователей, смену ролей, сброс пароля), оно
 * выдаётся ролью, а не персональной надстройкой к доступу к данным.
 */
export interface ModuleDef {
  code: string;
  label: string;
  /** есть {code}.export — выдаётся уже на уровне «Наблюдать» */
  hasExport: boolean;
  /** есть {code}.edit — без него уровень «Редактировать» бессмысленен */
  hasEdit: boolean;
  /** есть {code}.import — идёт в комплекте с edit */
  hasImport: boolean;
}

export const MODULE_REGISTRY = [
  { code: 'dashboard',    label: 'Дашборд',                     hasExport: true,  hasEdit: true,  hasImport: false },
  // Компании — доступ к карточке/рабочему пространству компании
  // (companies.view). Модуля в сетке не было вовсе, поэтому самый частый
  // сценарий — «пусть видит только свою компанию и больше ничего» — нельзя
  // было ни выдать, ни забрать. companies.create/delete сеткой не управляются:
  // это администрирование портфеля, оно идёт ролью.
  { code: 'companies',    label: 'Компании (карточка и рабочее пространство)', hasExport: false, hasEdit: true, hasImport: false },
  // Экран министра: только чтение — на /executive-dashboard нет ни одного
  // пишущего действия, поэтому уровень «Редактировать» ему недоступен.
  { code: 'exec_dashboard', label: 'Executive Dashboard', hasExport: false, hasEdit: false, hasImport: false },
  // Сводный обзор портфеля: чтение данных обзора. Заполнение печатной формы
  // («Заполнить отчёт») живёт в отдельном модуле «Задачи» (/overview-matrix
  // под tasks.edit), поэтому .edit у обзора нет — иначе сетка выдавала бы
  // право, которого не спрашивает ни один эндпоинт.
  { code: 'exec_overview', label: 'Сводный обзор портфеля',      hasExport: false, hasEdit: false, hasImport: false },
  { code: 'bp',           label: 'Бизнес-план',                 hasExport: false, hasEdit: true,  hasImport: true  },
  { code: 'kpi',          label: 'KPI',                         hasExport: false, hasEdit: true,  hasImport: true  },
  { code: 'financials',   label: 'Финансы (МСФО/НСБУ)',         hasExport: true,  hasEdit: true,  hasImport: true  },
  // SOE Health Check: чтение светофорной оценки + правка глобальных порогов
  // методики (PUT /financials/soe-health/params) — отсюда hasEdit.
  { code: 'soe_health',   label: 'SOE Health Check Tool',       hasExport: false, hasEdit: true,  hasImport: false },
  // Удельная себестоимость: чтение обзора + правка цен энергоносителей и
  // данных компании (PUT /unit-cost/prices, /unit-cost/companies/{code}).
  // Импорта нет: нормы заводятся через редактор, отдельного .import-кода нет.
  { code: 'unit_cost',    label: 'Удельная себестоимость',      hasExport: false, hasEdit: true,  hasImport: false },
  { code: 'credit',       label: 'Кредитный портфель',          hasExport: false, hasEdit: true,  hasImport: true  },
  { code: 'invest',       label: 'Инвест-проекты',              hasExport: true,  hasEdit: true,  hasImport: false },
  { code: 'procurement',  label: 'Закупки',                     hasExport: false, hasEdit: true,  hasImport: false },
  { code: 'esg',          label: 'ESG',                         hasExport: false, hasEdit: true,  hasImport: true  },
  { code: 'governance',   label: 'Корпуправление',              hasExport: false, hasEdit: true,  hasImport: false },
  { code: 'ratings',      label: 'Рейтинги',                    hasExport: false, hasEdit: true,  hasImport: true  },
  { code: 'procurement_analysis', label: 'Анализ закупок',      hasExport: true,  hasEdit: true,  hasImport: false },
  { code: 'consultants',  label: 'Консультанты',                hasExport: true,  hasEdit: true,  hasImport: false },
  { code: 'tasks',        label: 'Задачи',                      hasExport: false, hasEdit: true,  hasImport: false },
  { code: 'pmo',          label: 'PMO (расписание/Гантт)',      hasExport: true,  hasEdit: true,  hasImport: false },
  { code: 'reports',      label: 'Отчёты',                      hasExport: true,  hasEdit: false, hasImport: false },
  { code: 'monitoring',   label: 'Мониторинг (Execution Summary)', hasExport: true, hasEdit: true, hasImport: false },
  { code: 'ai',           label: 'AI-чат',                      hasExport: false, hasEdit: false, hasImport: false },
] as const satisfies readonly ModuleDef[];

export type ModuleCode = typeof MODULE_REGISTRY[number]['code'];

/** Канонический код прав модуля: сетка показывает invest, права живут на investment. */
export function canonicalModuleCode(moduleCode: string): string {
  return MODULE_CODE_ALIASES[moduleCode] || moduleCode;
}

export function moduleDef(moduleCode: string): ModuleDef | undefined {
  return MODULE_REGISTRY.find(m => m.code === moduleCode);
}

/**
 * Можно ли выдать модулю уровень «Редактировать». Для ai, reports,
 * exec_dashboard и exec_overview в каталоге нет ни .edit, ни .import — выбор
 * «Редактировать» не изменил бы ничего, поэтому в сетке он заблокирован.
 */
export function moduleSupportsWrite(moduleCode: string): boolean {
  const def = moduleDef(moduleCode);
  return !!def && (def.hasEdit || def.hasImport);
}
