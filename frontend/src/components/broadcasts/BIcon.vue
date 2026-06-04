<script setup lang="ts">
/**
 * BIcon — лёгкий inline-SVG icon set (stroke-only, 2px) для раздела рассылок.
 * Заменяет Tabler-иконки (`ti ti-*`), которые в проекте не подключены и
 * рендерились пустыми. Соответствует дизайн-системе: только SVG, без шрифтов.
 */
import { computed } from "vue";

const props = withDefaults(defineProps<{ name: string; size?: number | string }>(), {
  size: 16,
});

// Внутренняя разметка каждой иконки (viewBox 0 0 24 24, stroke=currentColor).
const PATHS: Record<string, string> = {
  speakerphone: '<path d="M3 10v4a1 1 0 0 0 1 1h2l3.5 3.5a1 1 0 0 0 1.5-.9V6.4a1 1 0 0 0-1.5-.9L6 9H4a1 1 0 0 0-1 1Z"/><path d="M15 8a4 4 0 0 1 0 8"/><path d="M17.5 5.5a8 8 0 0 1 0 13"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  x: '<path d="M18 6 6 18M6 6l12 12"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
  send: '<path d="M22 2 11 13M22 2l-7 20-4-9-9-4 20-7Z"/>',
  edit: '<path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5Z"/>',
  "chart-bar": '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
  "arrow-left": '<path d="M19 12H5M12 19l-7-7 7-7"/>',
  "external-link": '<path d="M15 3h6v6M21 3l-9 9M10 5H5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-5"/>',
  lock: '<rect x="4" y="11" width="16" height="9" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
  pin: '<path d="M9 4h6M10 4l-.7 6.2a4 4 0 0 1-1.5 2.6L6 14h12l-1.8-1.2a4 4 0 0 1-1.5-2.6L14 4M12 14v6"/>',
  power: '<path d="M12 4v8"/><path d="M7.5 7a7 7 0 1 0 9 0"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  alarm: '<circle cx="12" cy="13" r="7"/><path d="M12 10v3l2 2"/><path d="M5 3 2 6M22 6l-3-3"/>',
  "test-pipe": '<path d="M14 3v10.5a4 4 0 1 1-4 0V3"/><path d="M9 3h6"/><path d="M10 13h4"/>',
  trash: '<path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6"/>',
};

const inner = computed(() => PATHS[props.name] || "");
</script>

<template>
  <svg
    :width="size" :height="size" viewBox="0 0 24 24"
    fill="none" stroke="currentColor" stroke-width="2"
    stroke-linecap="round" stroke-linejoin="round"
    aria-hidden="true" v-html="inner"
    style="flex-shrink:0; vertical-align:-0.15em;"
  />
</template>
