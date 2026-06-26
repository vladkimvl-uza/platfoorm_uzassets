<script setup lang="ts">
/**
 * ExecDashDirectionsBlock — Row 3 left.
 * "По направлениям" — список направлений с прогресс-баром, проекты/задачи числа.
 *
 * Как в легасие Row 3 left (showExecDashView):
 *   - Цветная полоса слева 3px высотой 14px (color направления)
 *   - Имя направления (truncate)
 *   - Прогресс-бар 44px шириной
 *   - %, projects done/total, tasks done/total
 */
import { computed, ref } from "vue";
import { useExecutiveDashboard } from "@/composables/useExecutiveDashboard";
import DirectionDrillModal from "@/components/UZA/DirectionDrillModal.vue";
import { pctColor as pctColorBase } from "@/utils/pctColor";
import UzaStateBlock from "@/components/UZA/UzaStateBlock.vue";

const exec = useExecutiveDashboard();

const directions = computed(() => exec.data.value?.directions || []);

// Year-fallback: бэкенд вернул данные за другой год (за текущий FY пусто) —
// показываем бейдж с фактическим годом вместо пустой карточки.
const fallbackYear = computed(() => {
  const dy = exec.data.value?.directions_year ?? null;
  return dy && dy !== exec.year.value ? dy : null;
});

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

const pctColor = (pct: number) => pctColorBase(pct, 70, 35);

// Заливка прогресс-бара — мягкая пастель (единый стиль с барами KPI/исполнения).
// Отдельно от pctColor, который остаётся для ЧИСЛА % (там нужен контраст).
function barColor(pct: number): string {
  if (pct >= 70) return "#5DC093";
  if (pct >= 35) return "#EFB373";
  return "#E2807F";
}

function fmtCell(done: number, total: number): { text: string; color: string } {
  if (total === 0) return { text: "—", color: "#6B6A66" };
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
      <span v-if="fallbackYear" class="edd-badge" :title="`За FY ${exec.year.value} данных нет — показан последний доступный год`">
        данные за FY {{ fallbackYear }}
      </span>
    </div>

    <!-- Empty state -->
    <UzaStateBlock
      v-if="!directions.length"
      state="empty"
      variant="block"
      title="Нет направлений"
      :desc="`Для FY ${exec.year.value} нет данных о направлениях`"
    />

    <!-- Table -->
    <template v-else>
      <div class="edd-table-hdr edd-grid">
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
          class="edd-row edd-row--clickable edd-grid"
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
                  '--c': barColor(d.progress_pct),
                  '--d': `${i * 50}ms`,
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
  background: var(--bg1, #fff);
  border-radius: 12px;
  border: 1px solid rgba(0, 0, 0, 0.05);
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
  font-size: 11px;
  font-weight: 600;
  color: var(--t3, var(--t-muted));
  text-transform: uppercase;
  letter-spacing: 0.07em;
  flex: 1;
}
.edd-badge {
  flex-shrink: 0;
  font-size: 10.5px;
  font-weight: 700;
  color: #7F77DD;
  background: rgba(127, 119, 221, 0.10);
  border-radius: 999px;
  padding: 2px 8px;
  white-space: nowrap;
  letter-spacing: 0.02em;
}

.edd-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #6B6A66;
  font-size: 12px;
  padding: 30px 10px;
  text-align: center;
}

/* Table — общий grid-шаблон для шапки и строк: бар · имя(1fr) · 3 числовые
   колонки на clamp() (ужимаются на узкой карточке: блок живёт в колонке от
   280px). Имя получает остаток и переносится по словам, не схлопываясь. */
.edd-grid {
  display: grid;
  /* Имя получает ненулевой floor (96px), иначе три фикс-колонки + бар + gap
     вытесняли 1fr-имя к нулю и название вставало столбиком по буквам. */
  grid-template-columns:
    3px minmax(96px, 1fr)
    clamp(54px, 7vw, 104px)
    clamp(40px, 5vw, 64px)
    clamp(40px, 5vw, 64px);
  align-items: center;
  gap: clamp(6px, 0.6vw, 8px);
}
.edd-table-hdr {
  padding: 0 10px 4px;
  border-bottom: 0.5px solid rgba(0, 0, 0, 0.08);
  flex-shrink: 0;
}
.edd-th-bar {
  width: 3px;
}
.edd-th-cell {
  text-align: center;
  /* ужимаем заголовки на узкой карточке, чтобы «Проекты»/«Задачи» не вылезали
     за свою clamp-колонку */
  font-size: clamp(9px, 1.4vw, 11px);
  font-weight: 700;
  color: var(--t3, var(--t-muted));
  letter-spacing: 0.04em;
  text-transform: uppercase;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
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
  transition: background 0.15s;
  animation: eddRowIn 0.4s var(--ease-standard) var(--rd, 0ms) both;
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
}

.edd-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--t1, #1E2A4A);
  min-width: 0;  /* grid minmax(0,1fr) трек — имя занимает остаток ширины */
  /* Не сокращаем названия направлений — переносим на 2 строки.
     break-word (а НЕ anywhere): перенос по словам, в крайнем случае по слову —
     иначе при узкой колонке имя вставало в столбик по буквам. */
  white-space: normal;
  overflow-wrap: break-word;
  word-break: normal;
  hyphens: none;
  line-height: 1.25;
}

.edd-cell {
  text-align: center;
  font-feature-settings: "tnum";
  font-size: 12px;
  font-weight: 700;
  white-space: nowrap;
}
.edd-cell-progress {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-width: 0;
}
.edd-cell-num {
  min-width: 0;
}

.edd-pbar {
  width: clamp(34px, 4.6vw, 64px);
  height: 6px;
  background: var(--surface-2, #EEF1F7);
  border-radius: 99px;
  overflow: hidden;
  flex-shrink: 0;
}
.edd-pbar-fill {
  height: 6px;
  border-radius: 99px;
  background-color: var(--c, #7F77DD);
  background-image: linear-gradient(180deg, rgba(255, 255, 255, .5), rgba(255, 255, 255, 0) 70%);
  transform-origin: left center;
  animation: eddBarGrow .85s cubic-bezier(.34, 1.05, .64, 1) var(--d, 0ms) both;
}
@keyframes eddBarGrow { from { transform: scaleX(0); } to { transform: scaleX(1); } }
@media (prefers-reduced-motion: reduce) { .edd-pbar-fill { animation: none; } }
.edd-pct {
  font-size: 12px;
  font-weight: 700;
  min-width: 0;
  text-align: right;
  white-space: nowrap;
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
