<script setup lang="ts">
/**
 * ExecDashSectorGrid — Row 1: ИСПОЛНЕНИЕ ЗАДАЧ ОЖИДАНИЙ АКЦИОНЕРА.
 * Grid 5 columns с sector cards.
 *
 * Pack 7.29: вместо немедленного router.push открываем CompanyDrillModal
 * (Вариант A) с inline-редактированием для админов. Кнопка «Перейти к
 * компании» внутри модалки делает фактический router.push.
 */
import { computed, ref } from "vue";
import { useExecutiveDashboard } from "@/composables/useExecutiveDashboard";
import { useNumberTween } from "@/composables/useNumberTween";
import ExecDashSectorCard from "./ExecDashSectorCard.vue";
import CompanyDrillModal from "@/components/UZA/CompanyDrillModal.vue";
import ExecCopilot from "./ExecCopilot.vue";

const exec = useExecutiveDashboard();

const sectors = computed(() => exec.data.value?.sectors || []);

// 2026-05-26: rebuild header subtitle from bottom_metrics with countup animation
// (was backend pre-formatted string — couldn't tween). Falls back to raw
// string from backend if bottom_metrics not loaded yet.
const bm = computed(() => exec.data.value?.bottom_metrics);
const tTaskCount   = useNumberTween(() => Number(bm.value?.task_count) || 0, { duration: 900 });
const tDoneTasks   = useNumberTween(() => Number(bm.value?.done_tasks) || 0, { duration: 900 });
const tAvgProgress = useNumberTween(() => Number(bm.value?.avg_completion) || 0, { duration: 900 });

const headerSub = computed(() => {
  const d = exec.data.value;
  if (!d) return "";
  if (!bm.value) return d.row1_subtitle;
  return `${Math.round(tTaskCount.value)} задач · ${Math.round(tDoneTasks.value)} завершено · ${Math.round(tAvgProgress.value)}% средний прогресс`;
});

// ─── Modal state ───
interface DrillPayload {
  company_id: string;
  board_id: string | null;
  name: string;
  pct: number;
  task_total: number;
  task_done: number;
  sector_color: string;
  sector_label: string;
}
const drill = ref<DrillPayload | null>(null);

function onSelectCompany(payload: DrillPayload) {
  drill.value = payload;
}
function closeDrill() {
  drill.value = null;
}
</script>

<template>
  <div class="ed-card">
    <!-- Header -->
    <div class="ed-card-ttl">
      <span>
        <span>{{ exec.data.value?.row1_title || 'Исполнение задач Ожиданий Акционера' }}</span>
        · {{ exec.year.value }}
      </span>
      <span class="sub">{{ headerSub }}</span>
      <ExecCopilot :year="exec.year.value" />
    </div>

    <!-- Grid -->
    <div v-if="sectors.length" class="va-sec-grid">
      <ExecDashSectorCard
        v-for="(sec, i) in sectors"
        :key="sec.id"
        :sector="sec"
        :stagger-delay="i * 90"
        @select-company="onSelectCompany"
      />
    </div>
    <div v-else class="ed-empty">
      Нет данных о задачах для FY {{ exec.year.value }}
    </div>

    <!-- Drill-down modal (Pack 7.29) -->
    <CompanyDrillModal
      v-if="drill"
      :company-id="drill.company_id"
      :board-id="drill.board_id"
      :sector-color="drill.sector_color"
      :sector-label="drill.sector_label"
      :initial-name="drill.name"
      :initial-pct="drill.pct"
      :task-total="drill.task_total"
      :task-done="drill.task_done"
      @close="closeDrill"
    />
  </div>
</template>

<style scoped>
.ed-card {
  background: var(--bg1, #fff);
  border-radius: 12px;
  border: 1px solid rgba(0, 0, 0, 0.05);
  padding: 18px 20px 16px;
  margin-bottom: 14px;
  box-shadow: 0 4px 14px rgba(15, 23, 60, 0.04);
}

.ed-card-ttl {
  font-size: 11px;
  font-weight: 600;
  color: var(--t3, var(--t-muted));
  text-transform: uppercase;
  letter-spacing: 0.07em;
  margin: 0 0 14px;
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 14px;
  flex-wrap: wrap;
}

.ed-card-ttl .sub {
  font-size: 11.5px;
  color: #6B6A66;
  font-weight: 500;
  text-transform: none;
  letter-spacing: 0;
  font-feature-settings: "tnum";
}

.va-sec-grid {
  display: grid;
  /* Pack 7.9.2: auto-fit с min-width 200px вместо жёстких breakpoints.
     При типичной ширине ~1300-1500px все 5 секторов помещаются в один ряд.
     На очень узких экранах автоматически переключается на 2-3 колонки. */
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 10px;
}

.ed-empty {
  padding: 50px 20px;
  text-align: center;
  color: var(--t3, var(--t-muted));
  font-size: 12px;
  font-style: italic;
}

/* На совсем узких экранах принудительно 1 колонка для читабельности */
@media (max-width: 600px) {
  .va-sec-grid { grid-template-columns: 1fr; }
}
</style>
