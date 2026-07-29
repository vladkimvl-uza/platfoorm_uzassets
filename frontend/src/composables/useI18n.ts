/**
 * Компонентный доступ к переводам строк.
 *
 *   const { t, locale } = useI18n();
 *   <button :title="t('Сохранить')">{{ t("Сохранить") }}</button>
 *
 * t() реактивен: читает активную локаль из Pinia-стора во время рендера,
 * поэтому шаблон перерисовывается при смене языка. `locale` — для редких
 * случаев ветвления по языку (например, выбор name_uz вместо name_ru).
 */
import { computed } from "vue";

import { t } from "@/locale/i18n";
import type { AppLocale } from "@/locale/locales";
import { useLocaleStore } from "@/stores/locale";

export function useI18n() {
  const store = useLocaleStore();
  const locale = computed<AppLocale>(() => store.current);
  return { t, locale };
}
