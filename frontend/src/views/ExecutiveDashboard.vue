<script setup lang="ts">
import ExecDashCreditBlock from '@/components/Dashboard/ExecDashCreditBlock.vue'
/**
 * ExecutiveDashboard — главный view для /executive-dashboard.
 *
 * Pack 1: Row 0 (Topbar) + Row 1 (Sectors + Bottom metrics).
 * Pack 2: + Row 2 (Ratings + Execution chart).
 * Pack 3: + Row 2.5 — Финансы · МСФО.
 * Pack 4: + Row 3 — Направления · Корпуправление · Стандарты.
 */
import { onMounted } from "vue";
import { useExecutiveDashboard } from "@/composables/useExecutiveDashboard";
import { useAiPageContext } from "@/composables/useAiPageContext";
import ExecDashTopbar from "@/components/ExecDash/ExecDashTopbar.vue";
import ExecDashSectorGrid from "@/components/ExecDash/ExecDashSectorGrid.vue";
import ExecDashBenchmark from "@/components/ExecDash/ExecDashBenchmark.vue";
import ExecDashBottomMetrics from "@/components/ExecDash/ExecDashBottomMetrics.vue";
import ExecDashRatings from "@/components/ExecDash/ExecDashRatings.vue";
import ExecDashExecutionChart from "@/components/ExecDash/ExecDashExecutionChart.vue";
import ExecDashFinanceBlock from "@/components/ExecDash/ExecDashFinanceBlock.vue";
import ExecDashEconomicEffectBlock from "@/components/ExecDash/ExecDashEconomicEffectBlock.vue";
import ExecDashBPTrackerBlock from "@/components/ExecDash/ExecDashBPTrackerBlock.vue";
import ExecDashTaxContributionBlock from "@/components/ExecDash/ExecDashTaxContributionBlock.vue";
import ExecDashDirectionsBlock from "@/components/ExecDash/ExecDashDirectionsBlock.vue";
import ExecDashGovernanceBlock from "@/components/ExecDash/ExecDashGovernanceBlock.vue";
import ExecDashStandardsBlock from "@/components/ExecDash/ExecDashStandardsBlock.vue";
import UzaSkeleton from "@/components/UZA/UzaSkeleton.vue";

const exec = useExecutiveDashboard();

onMounted(() => exec.loadData());

// Pack 7.9e: AI Bubble context for Executive Dashboard
useAiPageContext({
  key: "exec-dash",
  label: "Executive Dashboard",
  describeState: () => `Год ${exec.year.value}; секторы: ${(exec.selectedSectors.value || []).join(", ") || "все"}`,
  quickActions: [
    { label: "Сводка по портфелю", icon: "📊",
      prompt: "Дай аналитическую сводку по портфелю из 22 SOE: ключевые цифры, лидеры и отстающие, общая динамика. Используй get_kpi_summary." },
    { label: "Топ-3 риска по портфелю", icon: "⚠️",
      prompt: "Найди топ-3 риска в портфеле: где провал KPI, где просрочки концентрируются, где credit-risk. Конкретные компании + рекомендации." },
    { label: "IPO-готовность компаний", icon: "🎯",
      prompt: "Проанализируй IPO-готовность портфеля: какие компании ближе всего к IPO, какие блокеры (governance/ESG/KPI) у каждой из IPO-roadmap." },
    { label: "Сравни 2025 vs 2026", icon: "📈",
      prompt: "Используй compare_years чтобы сравнить выполнение задач 2025 vs 2026 и compare_companies по EBITDA. Сделай вывод." },
    { label: "Что важного сегодня?", icon: "🔥",
      prompt: "Что важного на сегодня: просроченные критичные задачи, недавние модерация-events, активные алерты. Используй list_overdue_tasks + get_moderation_queue + list_notifications." },
  ],
});
</script>

<template>
  <div class="ed-page">
    <ExecDashTopbar />

    <div class="ed-body">
      <!-- Loading state — premium skeleton (replaces text spinner) -->
      <div v-if="exec.loading.data && !exec.data.value" class="ed-skel-stack">
        <UzaSkeleton variant="block" width="100%" height="120px" />
        <UzaSkeleton variant="kpi" :cols="6" :stagger="70" />
        <div class="ed-skel-row-2">
          <UzaSkeleton variant="block" width="100%" height="320px" />
          <UzaSkeleton variant="block" width="100%" height="320px" />
        </div>
        <UzaSkeleton variant="block" width="100%" height="280px" />
        <UzaSkeleton variant="rows" :rows="5" rowHeight="56px" :stagger="60" />
      </div>

      <!-- Error state -->
      <div v-else-if="exec.error.value" class="ed-empty-state ed-empty-error">
        <div>Ошибка загрузки: {{ exec.error.value }}</div>
        <button class="ed-retry-btn" @click="exec.loadData()">Повторить</button>
      </div>

      <!-- Empty data -->
      <div
        v-else-if="!exec.data.value || (!exec.data.value.sectors.length && exec.data.value.bottom_metrics.task_count === 0)"
        class="ed-empty-state"
      >
        <div>Нет данных за FY {{ exec.year.value }}</div>
        <div v-if="exec.data.value?.available_years?.length" class="ed-empty-hint">
          Доступные годы: {{ exec.data.value.available_years.join(", ") }}
        </div>
      </div>

      <!-- Main content -->
      <template v-else>
        <!-- Бенчмаркинг выбранных компаний (если выбраны в пикере) -->
        <ExecDashBenchmark />

        <!-- Row 1 -->
        <ExecDashSectorGrid />
        <ExecDashBottomMetrics />

        <!-- Row 2: Ratings (left) + Execution chart (right) -->
        <div class="ed-row-2">
          <ExecDashRatings />
          <ExecDashExecutionChart />
        </div>

        <!-- Row 2.5: Финансы · МСФО (Pack 3) -->
        <ExecDashFinanceBlock />
        <!-- Hidden per user request 2026-05-25 — /credit-scenario/overview
             возвращает 500. Снять v-if="false" после починки бэка. -->
        <ExecDashCreditBlock v-if="false" />

        <!-- Row 2.55: Экономический эффект (Pack 5)
             Hidden per user request 2026-05-23 — оставлено с v-if="false"
             чтобы быстро вернуть, сняв флаг. -->
        <ExecDashEconomicEffectBlock v-if="false" />

        <!-- Row 2.6: BP-трекер (Pack 5) -->
        <ExecDashBPTrackerBlock />

        <!-- Row 2.7: Налоговый вклад (Pack 5) -->
        <ExecDashTaxContributionBlock />

        <!-- Row 3 (Pack 4): Направления · Корпуправление · Стандарты -->
        <div class="ed-row-3">
          <ExecDashDirectionsBlock />
          <ExecDashGovernanceBlock />
          <ExecDashStandardsBlock />
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.ed-page {
  background: #F4F3F9;
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  font-family: var(--font, system-ui);
}

.ed-body {
  padding: 16px 22px 28px;
  flex: 1;
  display: flex;
  flex-direction: column;
}

/* Row 2 grid */
.ed-row-2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
  margin-top: 14px;
}

/* Row 3 grid (Pack 4) — 3 равных колонки */
.ed-row-3 {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 14px;
  margin-top: 14px;
}

@media (max-width: 1300px) {
  .ed-row-2 { grid-template-columns: 1fr; }
  .ed-row-3 { grid-template-columns: 1fr; }
}
@media (max-width: 640px) {
  .ed-body { padding: 12px 12px calc(64px + env(safe-area-inset-bottom)); gap: 0; }
}

/* States */
.ed-empty-state {
  padding: 80px 20px;
  text-align: center;
  color: var(--t3, var(--t-muted));
  font-size: 13px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
}

/* 2026-05-26: skeleton-loader layout — mirror page structure for premium feel */
.ed-skel-stack {
  display: flex; flex-direction: column;
  gap: 14px;
  padding: 14px 0;
}
.ed-skel-row-2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}
@media (max-width: 1000px) {
  .ed-skel-row-2 { grid-template-columns: 1fr; }
}

.ed-empty-error { color: #C36868; }

.ed-empty-hint {
  font-size: 11.5px;
  color: #B4B2A9;
  font-feature-settings: "tnum";
}

.ed-spinner {
  width: 32px;
  height: 32px;
  border: 3px solid rgba(127, 119, 221, 0.18);
  border-top-color: #7F77DD;
  border-radius: 50%;
  animation: edSpin 0.7s linear infinite;
}

@keyframes edSpin { to { transform: rotate(360deg); } }

.ed-retry-btn {
  background: rgba(127, 119, 221, 0.10);
  color: #5b54b8;
  border: 1px solid rgba(127, 119, 221, 0.25);
  border-radius: 7px;
  font-size: 11.5px;
  font-weight: 600;
  padding: 7px 16px;
  cursor: pointer;
  font-family: inherit;
  transition: all 0.15s;
}
.ed-retry-btn:hover {
  background: rgba(127, 119, 221, 0.18);
  border-color: rgba(127, 119, 221, 0.40);
}
</style>
