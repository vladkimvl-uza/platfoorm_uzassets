<script setup lang="ts">
// Секторный monogram-аватар компании. Выровнен под kit .cmp-avatar:
// 2 буквы из названия + градиент по цвету сектора, тонкое белое кольцо + drop-shadow.
import { computed } from "vue";

const props = withDefaults(defineProps<{
  name?: string | null;
  code?: string | null;
  /** Цвет сектора (#hex). По умолчанию бренд-фиолетовый. */
  color?: string;
  /** Размер в px (квадрат). Kit default — 32. */
  size?: number;
}>(), {
  color: "#7F77DD",
  size: 32,
});

const initials = computed(() => {
  const s = (props.name || props.code || "?").trim();
  if (!s) return "?";
  const parts = s.split(/\s+/).filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return s.slice(0, 2).toUpperCase();
});
</script>

<template>
  <span
    class="uza-co-avatar"
    :title="name || code || ''"
    :style="{
      width: size + 'px',
      height: size + 'px',
      fontSize: Math.round(size * 0.36) + 'px',
      borderRadius: Math.round(size * 0.28) + 'px',
      '--co-c': color,
    }"
  >{{ initials }}</span>
</template>

<style scoped>
.uza-co-avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  font-weight: 600;
  letter-spacing: -0.01em;
  color: #fff;
  background: linear-gradient(135deg,
    var(--co-c, #7F77DD) 0%,
    color-mix(in srgb, var(--co-c, #7F77DD) 64%, #11142b) 100%);
  box-shadow: 0 2px 6px rgba(15, 23, 60, .10), inset 0 0 0 1px rgba(255, 255, 255, .06);
  user-select: none;
}
</style>
