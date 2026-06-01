<script setup lang="ts">
// D1 — секторный monogram-аватар компании.
// 2 буквы из названия + градиент по цвету сектора.
import { computed } from "vue";

const props = withDefaults(defineProps<{
  name?: string | null;
  code?: string | null;
  /** Цвет сектора (#hex). По умолчанию бренд-фиолетовый. */
  color?: string;
  /** Размер в px (квадрат). */
  size?: number;
}>(), {
  color: "#7F77DD",
  size: 28,
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
      borderRadius: Math.round(size * 0.24) + 'px',
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
  letter-spacing: .02em;
  color: #fff;
  background: linear-gradient(135deg,
    var(--co-c, #7F77DD) 0%,
    color-mix(in srgb, var(--co-c, #7F77DD) 68%, #11142b) 100%);
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, .12);
  user-select: none;
}
</style>
