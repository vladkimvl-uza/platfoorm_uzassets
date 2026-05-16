<script setup lang="ts">
/**
 * TabLoans — composer таба «Все кредиты».
 *
 * Layout:
 *   Row 1: LoansFilters (chips + status + counter)
 *   Row 2: LoansTable (sticky-header sortable таблица)
 *
 * LoanDetailModal монтируется в родительском CreditPortfolio.vue
 * (через teleport-singleton, чтобы анимация не сбрасывалась).
 */
import LoansFilters from "./LoansFilters.vue";
import LoansTable from "./LoansTable.vue";
</script>

<template>
  <div class="cp-loans-grid">
    <LoansFilters />
    <LoansTable />
  </div>
</template>

<style scoped>
.cp-loans-grid {
  display: flex;
  flex-direction: column;
  gap: 0;
}
</style>
