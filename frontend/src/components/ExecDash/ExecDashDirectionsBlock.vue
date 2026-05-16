<script setup lang="ts">
/**
 * ExecDashDirectionsBlock — Row 3 left.
 * "По направлениям" — список направлений с прогресс-баром, проекты/задачи числа.
 *
 *   - Цветная полоса слева 3px высотой 14px (color направления)
 *   - Имя направления (truncate)
 *   - Прогресс-бар 44px шириной
 *   - %, projects done/total, tasks done/total
 */
import { computed, ref } from "vue";
import { useExecutiveDashboard } from "@/composables/useExecutiveDashboard";
import DirectionDrillModal from "@/components/UZA/DirectionDrillModal.vue";

const exec = useExecutiveDashboard();

const directions = computed(() => exec.data.value?.directions || []);

// Pack 7.36: drill-down модалка для направлений
const drillCode = ref<string | null>(null);
const drillLabel = ref<string>("");
const drillColor = ref<string>("");
function openDrill(d: { id: string; label: string; color: string }) {
  drillCode.value = d.id;
  drillLabel.value = d.label;
  drillColor.value = d.color;
}
function closeDrill() {
  drillCode.value = null;
}
function onRowKeydown(e: KeyboardEvent, d: { id: string; label: string; color: string }) {
  if (e.key === "Enter" || e.key === " ") {
    e.preventDefault();
    openDrill(d);
  }
}

function pctColor(pct: number): string {
  if (pct >= 70) return "#1D9E75";
  if (pct >= 35) return "#EF9F27";
  return "#E24B4A";
}

function fmtCell(done: number, total: number): { text: string; color: string } {
  if (total === 0) return { text: "—", color: "#B4B2A9" };
  const pct = Math.round(done / total * 100);
  return {
    text: `${done}/${total}`,
    color: pct >= 70 ? "#1D9E75" : pct >= 35 ? "#EF9F27" : "#7F77DD",
  };
}
</script>

<template>
  <div class="ed-card edd-card">
    <!-- Header -->
    <div class="edd-hdr">
      <span class="edd-eyebrow">По направлениям</span>
    </div>

    <!-- Empty state -->
    <div v-if="!directions.length" class="edd-empty">
      Нет данных о направлениях за FY {{ exec.year.value }}
    </div>

    <!-- Table -->
    <template v-else>
      <div class="edd-table-hdr">
        <div class="edd-th-bar" />
        <div class="edd-th-label" />
        <div class="edd-th-cell">Прогресс</div>
        <div class="edd-th-cell">Проекты</div>
        <div class="edd-th-cell">Задачи</div>
      </div>

      <div class="edd-rows">
        <div
          v-for="(d, i) in directions"
          :key="d.id"
          class="edd-row edd-row--clickable"
          :style="{ '--rd': `${i * 50}ms` }"
          role="button"
          tabindex="0"
          :title="'Подробнее: ' + d.label"
          @click="openDrill(d)"
          @keydown="onRowKeydown($event, d)"
        >
          <div class="edd-bar" :style="{ background: d.color }" />
          <span class="edd-label" :title="d.label">{{ d.label }}</span>

          <div class="edd-cell edd-cell-progress">
            <div class="edd-pbar">
              <div
                class="edd-pbar-fill"
                :style="{
                  width: `${d.progress_pct}%`,
                  background: pctColor(d.progress_pct),
                }"
              />
            </div>
            <span
              class="edd-pct"
              :style="{ color: pctColor(d.progress_pct) }"
            >{{ d.progress_pct }}%</span>
          </div>

          <div
            class="edd-cell edd-cell-num"
            :style="{ color: fmtCell(d.projects_done, d.projects_total).color }"
          >{{ fmtCell(d.projects_done, d.projects_total).text }}</div>

          <div
            class="edd-cell edd-cell-num"
            :style="{ color: fmtCell(d.tasks_done, d.tasks_total).color }"
          >{{ fmtCell(d.tasks_done, d.tasks_total).text }}</div>
        </div>
      </div>
    </template>

    <!-- Pack 7.36: drill modal -->
    <DirectionDrillModal
      v-if="drillCode"
      :direction-code="drillCode"
      :year="exec.year.value"
      :fallback-label="drillLabel"
      :fallback-color="drillColor"
      @close="closeDrill"
    />
  </div>
</template>

<style scoped>
.edd-card {
  display: flex;
  flex-direction: column;
  min-height: 420px;
  padding: 14px 14px 12px;
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 4px 14px rgba(15, 23, 60, 0.06);
  /* Pack 7.21: prevent grid column from expanding past 1fr allotment */
  min-width: 0;
  overflow: hidden;
}

.edd-hdr {
  display: flex;
  align-items: center;
  padding: 0 0 8px;
  gap: 8px;
  flex-shrink: 0;
}
.edd-eyebrow {
  font-size: 12.5px;
  font-weight: 700;
  color: #888780;
  text-transform: uppercase;
  letter-spacing: 0.07em;
  flex: 1;
}

.edd-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #B4B2A9;
  font-size: 12px;
  padding: 30px 10px;
  text-align: center;
}

/* Table */
.edd-table-hdr {
  display: flex;
  align-items: center;
  padding: 0 10px 4px;
  border-bottom: 0.5px solid rgba(0, 0, 0, 0.08);
  gap: 8px;
  flex-shrink: 0;
}
.edd-th-bar {
  width: 3px;
  flex-shrink: 0;
}
.edd-th-label {
  flex: 1;
}
.edd-th-cell {
  width: 76px;
  text-align: center;
  font-size: 11px;
  font-weight: 700;
  color: #888780;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  flex-shrink: 0;
  white-space: nowrap;
}
.edd-th-cell:first-of-type {
  width: 100px;
}

.edd-rows {
  display: flex;
  flex-direction: column;
  margin-top: 4px;
}

.edd-row {
  padding: 7px 10px;
  border-radius: 8px;
  margin-bottom: 1px;
  display: flex;
  align-items: center;
  gap: 8px;
  transition: background 0.15s;
  animation: eddRowIn 0.4s cubic-bezier(0.34, 1.2, 0.64, 1) var(--rd, 0ms) both;
  min-width: 0;  /* Pack 7.21: enable child ellipsis */
}
.edd-row:hover {
  background: rgba(127, 119, 221, 0.05);
}

/* Pack 7.36: clickable variant — for drill modal opening */
.edd-row--clickable {
  cursor: pointer;
  outline: none;
}
.edd-row--clickable:focus-visible {
  box-shadow: 0 0 0 2px rgba(127, 119, 221, 0.40);
}
.edd-row--clickable:active {
  background: rgba(127, 119, 221, 0.10);
}

.edd-bar {
  width: 3px;
  height: 14px;
  flex-shrink: 0;
}

.edd-label {
  font-size: 13px;
  font-weight: 500;
  color: #1E2A4A;
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
}

.edd-cell {
  text-align: center;
  flex-shrink: 0;
  font-feature-settings: "tnum";
  font-size: 12px;
  font-weight: 700;
}
.edd-cell-progress {
  width: 100px;
  display: flex;
  align-items: center;
  gap: 6px;
}
.edd-cell-num {
  width: 76px;
}

.edd-pbar {
  width: 44px;
  height: 4px;
  background: rgba(0, 0, 0, 0.06);
  border-radius: 4px;
  overflow: hidden;
  flex-shrink: 0;
}
.edd-pbar-fill {
  height: 4px;
  border-radius: 4px;
  transition: width 0.6s cubic-bezier(0.34, 1.2, 0.64, 1);
}
.edd-pct {
  font-size: 12px;
  font-weight: 700;
  min-width: 40px;
  text-align: right;
}

@keyframes eddRowIn {
  from {
    opacity: 0;
    transform: translateX(-8px);
  }
  to {
    opacity: 1;
    transform: translateX(0);
  }
}
</style>
