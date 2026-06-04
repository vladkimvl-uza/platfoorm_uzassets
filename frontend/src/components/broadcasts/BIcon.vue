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
  // ── moderation set ──
  "arrow-right": '<path d="M5 12h14M12 5l7 7-7 7"/>',
  "chevron-right": '<path d="m9 6 6 6-6 6"/>',
  eye: '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/>',
  history: '<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 4v4h4"/><path d="M12 8v4l3 2"/>',
  inbox: '<path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5 5h14l3 7v6a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1v-6l3-7Z"/>',
  "info-circle": '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>',
  package: '<path d="M21 8 12 3 3 8v8l9 5 9-5V8Z"/><path d="M3 8l9 5 9-5M12 13v8"/>',
  paperclip: '<path d="M21 11.5 12.5 20a5 5 0 0 1-7-7L14 4.5a3.3 3.3 0 0 1 4.7 4.7L10 18"/>',
  refresh: '<path d="M21 12a9 9 0 1 1-3-6.7L21 8"/><path d="M21 3v5h-5"/>',
  route: '<circle cx="6" cy="19" r="2.5"/><circle cx="18" cy="5" r="2.5"/><path d="M8.5 19H14a4 4 0 0 0 0-8H10a4 4 0 0 1 0-8h5.5"/>',
  "shield-check": '<path d="M12 3 5 6v6c0 4 3 7 7 9 4-2 7-5 7-9V6l-7-3Z"/><path d="m9 12 2 2 4-4"/>',
  "user-check": '<circle cx="9" cy="8" r="3.5"/><path d="M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6"/><path d="m16 11 2 2 4-4"/>',
  "user-exclamation": '<circle cx="9" cy="8" r="3.5"/><path d="M3 20c0-3.3 2.7-6 6-6s4 .6 5 1.5"/><path d="M19 8v4M19 16h.01"/>',
  // ── module icons (MODERATABLE_MODULES catalog) ──
  "chart-line": '<path d="M4 4v16h16"/><path d="m7 14 3-3 3 3 5-6"/>',
  cash: '<rect x="2" y="6" width="20" height="12" rx="2"/><circle cx="12" cy="12" r="2.5"/><path d="M6 9v6M18 9v6"/>',
  "chart-pie": '<path d="M12 3a9 9 0 1 0 9 9h-9V3Z"/><path d="M14 3.2A9 9 0 0 1 20.8 10H14V3.2Z"/>',
  leaf: '<path d="M4 20c0-9 7-15 16-15 0 9-6 16-16 15Z"/><path d="M9 15c2-3 5-5 8-6"/>',
  "building-bank": '<path d="M3 21h18M5 21V10M19 21V10M4 10h16L12 4 4 10ZM9 21v-6M15 21v-6"/>',
  "shopping-cart": '<circle cx="9" cy="20" r="1.5"/><circle cx="18" cy="20" r="1.5"/><path d="M2 3h3l2.5 12.5h11L21 7H6"/>',
  award: '<circle cx="12" cy="9" r="6"/><path d="m8.5 13.5-1.5 7 5-3 5 3-1.5-7"/>',
  checklist: '<path d="M9 6h11M9 12h11M9 18h11"/><path d="m3 6 1.5 1.5L7 5M3 12l1.5 1.5L7 11M3 18l1.5 1.5L7 17"/>',
  "message-circle": '<path d="M21 11.5A8.5 8.5 0 0 1 7.5 19L3 20l1-4.5A8.5 8.5 0 1 1 21 11.5Z"/>',
  // ── API / dev set ──
  api: '<rect x="5" y="7" width="14" height="9" rx="2"/><path d="M9 7V4M15 7V4M12 16v4"/>',
  "book-2": '<path d="M5 4h11a2 2 0 0 1 2 2v14H7a2 2 0 0 1-2-2V4Z"/><path d="M7 16h11"/>',
  "building-arch": '<path d="M4 21V9l8-5 8 5v12"/><path d="M9 21v-5a3 3 0 0 1 6 0v5"/><path d="M2 21h20"/>',
  clipboard: '<rect x="6" y="4" width="12" height="16" rx="2"/><path d="M9 4a1 1 0 0 0 1 1h4a1 1 0 0 0 1-1"/>',
  construction: '<rect x="3" y="9" width="18" height="11" rx="1"/><path d="M3 9l3-5h12l3 5M8 9l4 11M16 9l-4 11"/>',
  copy: '<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h8"/>',
  download: '<path d="M12 3v12M7 11l5 5 5-5M5 21h14"/>',
  "file-code": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M10 12l-2 2 2 2M14 12l2 2-2 2"/>',
  "file-download": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M12 12v6M9 15l3 3 3-3"/>',
  "file-off": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M3 3l18 18"/>',
  key: '<circle cx="8" cy="8" r="5"/><path d="M11.5 11.5 21 21M16 16l3-3"/>',
  "loader-2": '<path d="M12 3a9 9 0 1 0 9 9"/>',
  pencil: '<path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5Z"/>',
  "player-pause": '<rect x="6" y="5" width="4" height="14" rx="1"/><rect x="14" y="5" width="4" height="14" rx="1"/>',
  "player-play": '<path d="M7 5l12 7-12 7V5Z"/>',
  plug: '<path d="M9 3v6M15 3v6M7 9h10v3a5 5 0 0 1-10 0V9ZM12 17v4"/>',
  robot: '<rect x="5" y="8" width="14" height="11" rx="3"/><path d="M12 4v4M8 13h.01M16 13h.01M9 17h6"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/>',
  "search-off": '<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3M4 4l16 16"/>',
  "shield-x": '<path d="M12 3 5 6v6c0 4 3 7 7 9 4-2 7-5 7-9V6l-7-3Z"/><path d="m9.5 9.5 5 5M14.5 9.5l-5 5"/>',
  "terminal-2": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 9l3 3-3 3M13 15h4"/>',
  upload: '<path d="M12 21V9M7 13l5-5 5 5M5 3h14"/>',
  webhook: '<path d="M8.5 9a3.5 3.5 0 1 1 5 3.2L10 18"/><path d="M15 14a3.5 3.5 0 1 1-2.5 6H8"/><path d="M9.5 16a3.5 3.5 0 1 1-3.5-3.5"/>',
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
