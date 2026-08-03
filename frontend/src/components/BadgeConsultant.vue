<script setup lang="ts">
/**
 * Чип консультанта — ЕДИНЫЙ вид во всех таблицах и карточках.
 *
 * Было: у компонента своя палитра (KPMG #0091DA), у форензика своя (#0033A0),
 * у воркспейса третья (#378ADD) — одна компания выглядела по-разному на трёх
 * экранах; и рецепт чипа отличался от «Big 4» на /consultants (там фон
 * color+15 и рамка color+25, здесь был только фон color+18 без рамки).
 *
 * Стало: цвет и аббревиатура берутся из справочника консультантов — того же,
 * что рисует /consultants, — а рецепт чипа общий (`big4ChipStyle`). Локальная
 * палитра осталась запасной: работает, пока справочник не загрузился, и для
 * кодов, которых в нём нет.
 */
import { computed, onMounted, ref } from "vue";

import type { ConsultantBrief } from "@/api/consultants";
import { big4ChipStyle, ensureConsultants } from "@/utils/auditorStyle";

defineProps<{
  consultants: Array<{ id: string; abbr: string; color: string }> | string[] | null | undefined;
  size?: "sm" | "md";
}>();

// Fallback-палитра: до загрузки справочника и для кодов вне его
const DEFAULT_COLORS: Record<string, string> = {
  kpmg:       "#0091DA",
  pwc:        "#D04A02",
  ey:         "#FFE600",
  deloitte:   "#86BC25",
  mckinsey:   "#003A70",
  bcg:        "#177B57",
  rothschild: "#7C0007",
  cmt:        "#7F77DD",
  techenergy: "#EF9F27",
  degolyer:   "#888780",
  hpbs:       "#534AB7",
};
const DEFAULT_LABELS: Record<string, string> = {
  kpmg: "KPMG", pwc: "PwC", ey: "EY", deloitte: "DLT",
  mckinsey: "McK", bcg: "BCG", rothschild: "ROT",
  cmt: "CMT", techenergy: "TECH", degolyer: "DGY", hpbs: "HPB",
};

const catalog = ref<ConsultantBrief[]>([]);
onMounted(() => { void ensureConsultants().then((rows) => { catalog.value = rows; }); });

const byCode = computed(() => {
  const m: Record<string, ConsultantBrief> = {};
  for (const c of catalog.value) {
    if (c.code) m[c.code.toLowerCase()] = c;
    if (c.abbr) m[c.abbr.toLowerCase()] = c;
  }
  return m;
});

function normalize(c: any): { id: string; abbr: string; color: string } {
  if (typeof c === "string") {
    const k = c.toLowerCase();
    const hit = byCode.value[k];
    return {
      id: k,
      abbr: hit?.abbr || DEFAULT_LABELS[k] || c.toUpperCase().slice(0, 4),
      color: hit?.color_hex || DEFAULT_COLORS[k] || "#7F77DD",
    };
  }
  // Объект уже несёт цвет из данных экрана; если цвета нет — берём справочник.
  const hit = byCode.value[String(c.id || "").toLowerCase()]
    || byCode.value[String(c.abbr || "").toLowerCase()];
  return { ...c, color: c.color || hit?.color_hex || "#7F77DD" };
}
</script>

<template>
  <div v-if="consultants && consultants.length" class="cons-row" :class="`size-${size || 'md'}`">
    <span v-for="c in consultants.map(normalize)" :key="c.id"
          class="cons-pill"
          :style="big4ChipStyle(c.color)">
      {{ c.abbr }}
    </span>
  </div>
</template>

<style scoped>
.cons-row {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 3px;
}
.cons-pill {
  font-weight: 700;
  border-radius: 4px;
  border: 0.5px solid;
  white-space: nowrap;
  letter-spacing: 0.02em;
  line-height: 1.4;
}
.size-sm .cons-pill { font-size: 9px;  padding: 1px 4px; }
.size-md .cons-pill { font-size: 10px; padding: 1px 5px; }
</style>
