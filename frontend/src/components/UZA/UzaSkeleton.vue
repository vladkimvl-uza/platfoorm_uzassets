<script setup lang="ts">
/**
 * UzaSkeleton — universal shimmer placeholder.
 *
 * Используется вместо "Загрузка..." spinner-текста чтобы UI ощущался
 * мгновенно отзывчивым (perceived performance). Скелет повторяет форму
 * настоящего контента: blocks/rows/grids/circles.
 *
 * Variants:
 *   • <UzaSkeleton variant="line" width="60%" height="14px" />      — текст
 *   • <UzaSkeleton variant="block" width="100%" height="80px" />    — карточка
 *   • <UzaSkeleton variant="circle" size="48px" />                  — аватар/иконка
 *   • <UzaSkeleton variant="rows" :rows="6" rowHeight="42px" />     — список
 *   • <UzaSkeleton variant="kpi" :cols="4" />                       — KPI band
 *   • <UzaSkeleton variant="table" :rows="8" :cols="5" />           — таблица
 *
 * Респектит prefers-reduced-motion — анимация shimmer заменяется на
 * static neutral fill.
 */
defineProps<{
  variant?: "line" | "block" | "circle" | "rows" | "kpi" | "table";
  width?: string;
  height?: string;
  size?: string;
  rows?: number;
  cols?: number;
  rowHeight?: string;
  /** stagger delay between sub-items (ms). default 60 */
  stagger?: number;
}>();
</script>

<template>
  <!-- Single primitives -->
  <div
    v-if="variant === 'circle'"
    class="uza-sk uza-sk--circle"
    :style="{ width: size || '40px', height: size || '40px' }"
  />
  <div
    v-else-if="variant === 'line'"
    class="uza-sk uza-sk--line"
    :style="{ width: width || '100%', height: height || '14px' }"
  />
  <div
    v-else-if="variant === 'block'"
    class="uza-sk uza-sk--block"
    :style="{ width: width || '100%', height: height || '80px' }"
  />

  <!-- Composite: rows (list of lines) -->
  <div v-else-if="variant === 'rows'" class="uza-sk-rows">
    <div
      v-for="i in (rows || 6)"
      :key="i"
      class="uza-sk uza-sk--block"
      :style="{
        width: '100%',
        height: rowHeight || '42px',
        animationDelay: ((stagger ?? 60) * (i - 1)) + 'ms',
      }"
    />
  </div>

  <!-- Composite: KPI band (N columns of label+number) -->
  <div v-else-if="variant === 'kpi'" class="uza-sk-kpi">
    <div
      v-for="i in (cols || 4)"
      :key="i"
      class="uza-sk-kpi-cell"
      :style="{ animationDelay: ((stagger ?? 60) * (i - 1)) + 'ms' }"
    >
      <div class="uza-sk uza-sk--line" style="width:60%;height:9px;margin-bottom:8px;" />
      <div class="uza-sk uza-sk--line" style="width:50%;height:26px;border-radius:5px;" />
    </div>
  </div>

  <!-- Composite: table (header + N rows × M cols) -->
  <div v-else-if="variant === 'table'" class="uza-sk-table">
    <div class="uza-sk-table-row uza-sk-table-head">
      <div
        v-for="c in (cols || 5)"
        :key="`h-${c}`"
        class="uza-sk uza-sk--line"
        :style="{ width: '70%', height: '11px' }"
      />
    </div>
    <div
      v-for="r in (rows || 8)"
      :key="`r-${r}`"
      class="uza-sk-table-row"
      :style="{ animationDelay: ((stagger ?? 60) * (r - 1)) + 'ms' }"
    >
      <div
        v-for="c in (cols || 5)"
        :key="`c-${r}-${c}`"
        class="uza-sk uza-sk--line"
        :style="{ width: '85%', height: '13px' }"
      />
    </div>
  </div>

  <!-- Default: just a block -->
  <div
    v-else
    class="uza-sk uza-sk--block"
    :style="{ width: width || '100%', height: height || '80px' }"
  />
</template>

<style scoped>
/* ═══ Base shimmer ═══ */
.uza-sk {
  position: relative;
  overflow: hidden;
  background: linear-gradient(90deg, #F0EEF7 0%, #EFEDF6 100%);
  border-radius: 6px;
  /* fade-in when first appears */
  animation: uzaSkFadeIn 220ms ease both, uzaSkPulse 1.6s ease-in-out infinite;
}
.uza-sk::after {
  content: "";
  position: absolute;
  inset: 0;
  background: linear-gradient(
    90deg,
    transparent 0%,
    rgba(255, 255, 255, 0.55) 50%,
    transparent 100%
  );
  transform: translateX(-100%);
  animation: uzaSkShimmer 1.6s ease-in-out infinite;
}

.uza-sk--circle { border-radius: 50%; }
.uza-sk--line   { border-radius: 4px; }
.uza-sk--block  { border-radius: 10px; }

/* ═══ Composites ═══ */
.uza-sk-rows {
  display: flex; flex-direction: column; gap: 8px;
  width: 100%;
}
.uza-sk-kpi {
  display: grid;
  grid-template-columns: repeat(var(--cols, 4), 1fr);
  gap: 14px;
  padding: 16px;
  background: #fff;
  border-radius: 12px;
  border: 1px solid rgba(0, 0, 0, .05);
  box-shadow: 0 4px 14px rgba(15, 23, 60, .04);
}
.uza-sk-kpi-cell {
  display: flex; flex-direction: column;
  padding: 8px 14px;
  border-right: 1px solid rgba(0, 0, 0, .04);
}
.uza-sk-kpi-cell:last-child { border-right: none; }

.uza-sk-table {
  display: flex; flex-direction: column; gap: 6px;
  padding: 14px;
  background: #fff;
  border-radius: 12px;
  border: 1px solid rgba(0, 0, 0, .05);
}
.uza-sk-table-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(60px, 1fr));
  gap: 14px;
  padding: 8px 0;
  border-bottom: 0.5px solid rgba(0, 0, 0, .04);
}
.uza-sk-table-row:last-child { border-bottom: none; }
.uza-sk-table-head { padding-bottom: 12px; border-bottom: 1px solid rgba(0, 0, 0, .08); }

/* ═══ Animations ═══ */
@keyframes uzaSkFadeIn {
  from { opacity: 0; }
  to   { opacity: 1; }
}
@keyframes uzaSkShimmer {
  0%   { transform: translateX(-100%); }
  60%  { transform: translateX(120%); }
  100% { transform: translateX(120%); }
}
@keyframes uzaSkPulse {
  0%, 100% { background-color: #F0EEF7; }
  50%      { background-color: #EAE7F2; }
}

@media (prefers-reduced-motion: reduce) {
  .uza-sk, .uza-sk::after { animation: none !important; }
  .uza-sk::after { display: none; }
}
</style>
