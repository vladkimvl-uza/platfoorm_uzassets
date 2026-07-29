/**
 * Область доступа пользователя по компаниям — единый источник для интерфейса.
 *
 * Бэкенд отдаёт её в /auth/me (`scope_unrestricted` + `scope_companies`,
 * см. app/services/auth_user/service.py:_company_scope). Здесь она превращается
 * в три режима, по которым экраны решают, что показывать:
 *
 *   unrestricted  — видит весь портфель (владелец или право companies.view_all):
 *                   селекторы компаний и секторов, портфельные сводки и экран
 *                   министра доступны как раньше;
 *   single        — ровно одна компания: селекторы и портфельные срезы НЕ нужны,
 *                   данные сразу по своей компании;
 *   multi         — несколько компаний: селекторы нужны, но только со своими.
 *
 * Правило: `showCompanyPicker` и `showSectorPicker` — единственные признаки,
 * по которым экраны прячут фильтры. Не проверяйте роли напрямую: роль не
 * определяет область (её дают членство в группах, сектора и гранты).
 *
 * Использование:
 *   const scope = useCompanyScope();
 *   <UzaCompanyPicker v-if="scope.showCompanyPicker.value" :options="scope.companies.value" />
 *   const code = ref(scope.defaultCompanyCode.value);
 */
import { computed } from "vue";

import { useAuthStore } from "@/stores/auth";

export type CompanyScopeItem = {
  id: string;
  code: string;
  name: string;
  sector?: string | null;
};

export function useCompanyScope() {
  const auth = useAuthStore();

  /** Компании области (пусто, если пользователь видит весь портфель). */
  const companies = computed<CompanyScopeItem[]>(
    () => (auth.user?.scope_companies as CompanyScopeItem[] | undefined) || [],
  );

  /** Видит весь портфель. Владельца считаем портфельным всегда. */
  const unrestricted = computed<boolean>(
    () => !!auth.user?.is_owner || auth.user?.scope_unrestricted !== false,
  );

  /** Ограничен и ровно одной компанией. */
  const single = computed<boolean>(() => !unrestricted.value && companies.value.length === 1);

  /** Ограничен несколькими компаниями. */
  const multi = computed<boolean>(() => !unrestricted.value && companies.value.length > 1);

  /** Ограничен областью (одна или несколько компаний). */
  const restricted = computed<boolean>(() => !unrestricted.value);

  /**
   * Показывать ли селектор компаний. Одна компания — выбирать не из чего,
   * поэтому селектор скрыт и место в шапке не занимает.
   */
  const showCompanyPicker = computed<boolean>(() => unrestricted.value || multi.value);

  /**
   * Показывать ли селектор секторов. При единственной компании смысла нет;
   * при нескольких компаниях одного сектора — тоже (выбор из одного значения).
   */
  const showSectorPicker = computed<boolean>(() => {
    if (unrestricted.value) return true;
    if (!multi.value) return false;
    return new Set(companies.value.map((c) => c.sector || "")).size > 1;
  });

  /**
   * Показывать ли ПОРТФЕЛЬНЫЕ срезы: сводку в Бизнес-плане и KPI, сравнение
   * компаний, экран министра. Ограниченным пользователям они не нужны —
   * решение владельца 29.07.2026.
   */
  const showPortfolioViews = computed<boolean>(() => unrestricted.value);

  /** Код компании по умолчанию: своя единственная, иначе первая из своих. */
  const defaultCompanyCode = computed<string | null>(
    () => (unrestricted.value ? null : (companies.value[0]?.code ?? null)),
  );

  /** UUID компании по умолчанию — там, где экран работает по id. */
  const defaultCompanyId = computed<string | null>(
    () => (unrestricted.value ? null : (companies.value[0]?.id ?? null)),
  );

  /** Разрешена ли компания пользователю (для защиты от чужого кода в URL). */
  function allows(code: string | null | undefined): boolean {
    if (unrestricted.value) return true;
    if (!code) return false;
    return companies.value.some((c) => c.code === code);
  }

  return {
    companies,
    unrestricted,
    restricted,
    single,
    multi,
    showCompanyPicker,
    showSectorPicker,
    showPortfolioViews,
    defaultCompanyCode,
    defaultCompanyId,
    allows,
  };
}
