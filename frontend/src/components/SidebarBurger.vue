<script setup lang="ts">
// Переиспользуемый бургер для собственных топбаров страниц.
// На планшете/телефоне (≤1023) открывает off-canvas drawer, на десктопе —
// сворачивает рейку сайдбара. Инжекты приходят из AppShell (provide).
// ВАЖНО: страница, где он используется, должна быть в OWN_TOPBAR_PREFIXES
// (AppShell), иначе сверху будет ещё и плавающий гамбургер + пустой зазор.
import { inject } from "vue";
const toggleSidebar = inject<() => void>("toggleSidebar", () => {});
const openMobileSidebar = inject<() => void>("openMobileSidebar", () => {});
function onBurger() {
  if (typeof window !== "undefined" && window.innerWidth <= 1023) openMobileSidebar();
  else toggleSidebar();
}
</script>

<template>
  <button class="uza-pageburger" type="button" @click="onBurger()"
          title="Меню / свернуть сайдбар" aria-label="Меню">
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         stroke-width="2" stroke-linecap="round">
      <line x1="3" y1="6" x2="21" y2="6" /><line x1="3" y1="12" x2="21" y2="12" /><line x1="3" y1="18" x2="21" y2="18" />
    </svg>
  </button>
</template>

<style scoped>
.uza-pageburger {
  display: inline-flex; align-items: center; justify-content: center;
  width: 36px; height: 36px; flex-shrink: 0;
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.06);
  color: #fff; cursor: pointer;
  transition: background 0.14s ease, border-color 0.14s ease;
}
.uza-pageburger:hover { background: rgba(255, 255, 255, 0.12); border-color: rgba(255, 255, 255, 0.20); }
@media (pointer: coarse) { .uza-pageburger { width: 44px; height: 44px; } }
</style>
