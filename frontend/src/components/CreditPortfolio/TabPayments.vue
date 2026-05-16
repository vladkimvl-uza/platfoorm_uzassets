<script setup lang="ts">
/**
 * TabPayments — composer таба «Платежи».
 *
 * Layout:
 *   Row 1: PaymentsCalendarBars (stacked bars по годам × валютам)
 *   Row 2: PaymentsSankey (банк → год)
 */
import { useCreditData } from "@/composables/useCreditData";
import { fmtMoneyShort, toNum } from "@/api/credit";
import PaymentsCalendarBars from "./PaymentsCalendarBars.vue";
import PaymentsSankey from "./PaymentsSankey.vue";
import { computed } from "vue";

const credit = useCreditData();

const overdueAmt = computed(() => {
  if (credit.aggregate.value) return toNum(credit.aggregate.value.overdue_amount);
  return 0;
});
</script>

<template>
  <div class="cp-pay-grid">
    <!-- Row 1: Календарь bars -->
    <div class="pa-card">
      <div class="pa-card-h">
        <span class="pa-card-t">Календарь погашений</span>
        <span class="pa-card-s">
          stacked bars · разрез по валютам · клик по столбцу — фильтр по году
          <span v-if="overdueAmt > 0" class="cp-pay-overdue-hint">
            · просрочка {{ fmtMoneyShort(overdueAmt) }} включена в {{ credit.asOfYear.value }}
          </span>
        </span>
      </div>
      <PaymentsCalendarBars />
    </div>

    <!-- Row 2: Sankey -->
    <div class="pa-card">
      <div class="pa-card-h">
        <span class="pa-card-t">Поток платежей: банк → год</span>
        <span class="pa-card-s">
          топ-8 банков · клик по году/банку — фильтр · hover — детализация
        </span>
      </div>
      <PaymentsSankey />
    </div>
  </div>
</template>

<style scoped>
.cp-pay-grid {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.cp-pay-overdue-hint {
  color: #C97070;
  font-weight: 600;
}
</style>
