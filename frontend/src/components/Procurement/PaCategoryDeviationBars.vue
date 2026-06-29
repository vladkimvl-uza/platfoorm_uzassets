<script setup lang="ts">
/**
 * PaCategoryDeviationBars — отклонение цен по категориям как ДИВЕРЖЕНТНЫЕ
 * горизонтальные бары (замена radar/spider-чарта).
 *
 * Почему не radar: на 15+ осях паутина нечитаема (спайки искажают восприятие,
 * нельзя сравнить величины, отрицательные/положительные отклонения сливаются).
 * Дивержентные бары: одна строка = категория, бар влево (экономия, зелёный) или
 * вправо (переплата, красный) от нулевой оси; сортировка по убыванию отклонения.
 * Показываем только категории с сопоставимыми данными (cat_dev).
 */
import { computed } from "vue";
import {
  paColorByDev,
  paFmtMoneyShort,
  type CategoryDeviation,
} from "@/api/procurement_analysis";

const props = defineProps<{
  cats: CategoryDeviation[];
  /** Лимит строк (по умолчанию все). */
  maxRows?: number;
}>();

interface Row {
  id: string | number | null;
  name: string;
  dev: number;
  sumDev: number;
  count: number;
}

const rows = computed<Row[]>(() => {
  const list = (props.cats || [])
    .filter((c) => (Number(c.closure_count) || 0) > 0 || Number(c.sum_ref) > 0)
    .map((c) => ({
      id: c.category_id,
      name: c.category_name || c.category_short || "—",
      dev: Number(c.deviation_pct) || 0,
      sumDev: Number(c.sum_dev) || 0,
      count: Number(c.closure_count) || 0,
    }))
    .sort((a, b) => b.dev - a.dev);
  return props.maxRows ? list.slice(0, props.maxRows) : list;
});

// Масштаб полубара: максимум |отклонения| в наборе, но не менее 10% (иначе
// крошечные отклонения растягиваются на всю дорожку).
const maxAbs = computed(() =>
  Math.max(10, ...rows.value.map((r) => Math.abs(r.dev))),
);

/** Стиль заливки: от центра (50%) вправо при переплате, влево при экономии. */
function fillStyle(dev: number): Record<string, string> {
  const half = Math.min(50, (Math.abs(dev) / maxAbs.value) * 50);
  const color = paColorByDev(dev);
  if (dev >= 0) {
    return { left: "50%", width: half + "%", background: color };
  }
  return { left: 50 - half + "%", width: half + "%", background: color };
}

function devColor(dev: number): string {
  if (dev >= 10) return "#C53030";
  if (dev >= 0) return "#B07415";
  return "#0F6E56";
}
function fmtDev(dev: number): string {
  return (dev >= 0 ? "+" : "") + dev.toFixed(1) + "%";
}
</script>

<template>
  <div class="cdb">
    <div v-if="!rows.length" class="cdb-empty">Нет сопоставимых категорий</div>
    <div
      v-for="(r, i) in rows"
      :key="String(r.id) + r.name"
      class="cdb-row"
      :style="{ animationDelay: i * 30 + 'ms' }"
      :title="`${r.name}: ${fmtDev(r.dev)} · ${paFmtMoneyShort(r.sumDev)} сум · ${r.count} закуп.`"
    >
      <div class="cdb-name">{{ r.name }}</div>
      <div class="cdb-track">
        <span class="cdb-axis" />
        <span class="cdb-fill" :style="fillStyle(r.dev)" />
      </div>
      <div class="cdb-val" :style="{ color: devColor(r.dev) }">{{ fmtDev(r.dev) }}</div>
    </div>
    <div v-if="rows.length" class="cdb-legend">
      <span class="cdb-lg"><i style="background:#7DBFA1" /> экономия</span>
      <span class="cdb-lg-axis">0</span>
      <span class="cdb-lg"><i style="background:#E89B9A" /> переплата</span>
    </div>
  </div>
</template>

<style scoped>
.cdb { display: flex; flex-direction: column; gap: 3px; }

.cdb-empty {
  padding: 24px 16px; text-align: center;
  font-size: 12px; font-style: italic;
  color: var(--t3, var(--t-muted));
}

.cdb-row {
  display: grid;
  grid-template-columns: 150px 1fr 58px;
  align-items: center;
  gap: 10px;
  padding: 4px 2px;
  animation: cdbIn .35s var(--ease-standard, cubic-bezier(.22,1,.36,1)) backwards;
}
@keyframes cdbIn { from { opacity: 0; transform: translateY(3px); } to { opacity: 1; transform: none; } }

.cdb-name {
  font-size: 11.5px;
  color: var(--t1, #1e2a4a);
  text-align: right;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}

.cdb-track {
  position: relative;
  height: 14px;
  background: rgba(15, 23, 60, .04);
  border-radius: 3px;
  overflow: hidden;
}
.cdb-axis {
  position: absolute; top: 0; bottom: 0; left: 50%;
  width: 1px; background: rgba(15, 23, 60, .18);
  z-index: 1;
}
.cdb-fill {
  position: absolute; top: 2px; bottom: 2px;
  border-radius: 2px;
  animation: cdbGrow .6s var(--ease-standard, cubic-bezier(.22,1,.36,1)) both;
  transform-origin: left center;
}
@keyframes cdbGrow { from { transform: scaleX(0); } to { transform: scaleX(1); } }

.cdb-val {
  font-size: 11px;
  font-weight: 600;
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.cdb-legend {
  display: flex; align-items: center; justify-content: center;
  gap: 14px; margin-top: 8px;
  font-size: 9.5px; color: var(--t3, var(--t-muted));
  text-transform: uppercase; letter-spacing: .05em;
}
.cdb-lg { display: inline-flex; align-items: center; gap: 4px; }
.cdb-lg i { width: 9px; height: 9px; border-radius: 2px; display: inline-block; }
.cdb-lg-axis { color: rgba(15, 23, 60, .35); font-weight: 600; }

@media (prefers-reduced-motion: reduce) {
  .cdb-row, .cdb-fill { animation: none !important; }
}
</style>
