<template>
  <span v-if="name" class="sector-chip" :style="chipStyle" :title="t('Сектор: {value0}', { value0: name })">
    <span class="sector-chip__dot" :style="{ background: dotColor }"></span>
    {{ name }}
  </span>
</template>

<script setup lang="ts">
/**
 * SectorChip — единый чип сектора (название + точка цвета сектора).
 *
 * Пара к CompanyTicker: где показывается сектор компании — только через этот
 * компонент, чтобы стиль секторов был синхронен везде (таблицы, карточки, аудит).
 *
 * Цвет берётся из :color (sector_color из БД); при отсутствии — нейтральный.
 */
import { computed } from "vue";
import { useI18n } from "@/composables/useI18n";
const { t } = useI18n();


const props = withDefaults(
  defineProps<{
    name?: string | null;
    color?: string | null;
    size?: "sm" | "md";
  }>(),
  { size: "md" },
);

function hexToRgb(hex?: string | null): string | null {
  if (!hex) return null;
  let h = hex.trim().replace(/^#/, "");
  if (h.length === 3) h = h.split("").map((c) => c + c).join("");
  if (!/^[0-9a-fA-F]{6}$/.test(h)) return null;
  const n = parseInt(h, 16);
  return `${(n >> 16) & 255},${(n >> 8) & 255},${n & 255}`;
}

const dotColor = computed(() => props.color || "#94A3B8");
const chipStyle = computed(() => {
  const rgb = hexToRgb(props.color);
  return {
    background: rgb ? `rgba(${rgb},.10)` : "rgba(100,116,139,.10)",
    color: rgb ? props.color! : "#475569",
    fontSize: props.size === "sm" ? "10px" : "11px",
    padding: props.size === "sm" ? "1px 8px 1px 7px" : "2px 10px 2px 8px",
  };
});
</script>

<style scoped>
.sector-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border-radius: 999px;
  font-weight: 500;
  line-height: 1.5;
  white-space: nowrap;
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
}
.sector-chip__dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}
</style>
