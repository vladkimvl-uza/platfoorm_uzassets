<script setup lang="ts">
// D12 — плавающий переключатель темы. Монтируется отдельным app в main.ts,
// чтобы не трогать AppShell (его параллельно правит Claude Design).
import { currentTheme, toggleTheme } from "@/composables/useTheme";
</script>

<template>
  <button
    class="uza-theme-toggle"
    @click="toggleTheme"
    :title="currentTheme === 'dark' ? 'Светлая тема' : 'Тёмная тема'"
    aria-label="Переключить тему"
  >
    <svg v-if="currentTheme === 'dark'" width="18" height="18" viewBox="0 0 24 24"
         fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <circle cx="12" cy="12" r="5"/>
      <path d="M12 1v2M12 21v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M1 12h2M21 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4"/>
    </svg>
    <svg v-else width="18" height="18" viewBox="0 0 24 24"
         fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
    </svg>
  </button>
</template>

<style scoped>
.uza-theme-toggle {
  position: fixed;
  right: 18px;
  bottom: 18px;
  z-index: 99999;
  width: 42px;
  height: 42px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--glass-bg, rgba(255, 255, 255, .85));
  border: 1px solid var(--border2, rgba(99, 102, 180, .18));
  color: var(--t2, #334155);
  box-shadow: 0 6px 20px rgba(15, 23, 60, .14);
  cursor: pointer;
  backdrop-filter: blur(8px);
  transition: transform .14s, box-shadow .14s;
}
.uza-theme-toggle:hover {
  transform: translateY(-2px);
  box-shadow: 0 10px 28px rgba(15, 23, 60, .20);
}
</style>
