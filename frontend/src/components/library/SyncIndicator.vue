<script setup lang="ts">
/**
 * Sync source indicator — tiny colored dot showing which module owns the data.
 * Used in cells and mini-cards to make sync-flow visible at a glance.
 */
import { computed } from "vue";
import { i18nKey } from "@/locale/keys";
import { useI18n } from "@/composables/useI18n";
const { t } = useI18n();



const props = defineProps<{
  sourceModule: string | null;
  size?: number;
}>();

const size = computed(() => props.size ?? 6);

const meta = computed<{ color: string; label: string }>(() => {
  switch ((props.sourceModule || "").toLowerCase()) {
    case "finmodel":
    case "financials":  return { color: "#378ADD", label: i18nKey("Источник: FinModel") };
    case "kpi":         return { color: "#534AB7", label: i18nKey("Источник: KPI")      };
    case "credit":
    case "credits":     return { color: "#1D9E75", label: i18nKey("Источник: Кредитный портфель") };
    case "ratings":     return { color: "#7F77DD", label: i18nKey("Источник: Рейтинги") };
    case "bp":
    case "business_plan": return { color: "#A78BFA", label: i18nKey("Источник: БП") };
    case "procurement": return { color: "#0E7490", label: i18nKey("Источник: Закупки") };
    case "esg":         return { color: "#10B981", label: i18nKey("Источник: ESG") };
    case "governance":  return { color: "#94A3B8", label: i18nKey("Источник: Корп. упр.") };
    case "companies":   return { color: "#1E2A4A", label: i18nKey("Источник: Карточка компании") };
    case null:
    case "":            return { color: "#FAC775", label: i18nKey("Custom · только в библиотеке") };
    default:            return { color: "#FAC775", label: t("Источник: {source}", { source: props.sourceModule }) };
  }
});
</script>

<template>
  <span
    class="cl-sync-dot"
    :style="{
      width:  size + 'px',
      height: size + 'px',
      background: meta.color,
    }"
    :title="t(meta.label)"
  ></span>
</template>

<style scoped>
.cl-sync-dot {
  display: inline-block;
  border-radius: 50%;
  flex-shrink: 0;
  vertical-align: middle;
}
</style>
