<script setup lang="ts">
/**
 * AppTopbar — глобальный topbar приложения UzAssets, dual-mode.
 *
 * Mode "dashboard" (только на /dashboard):
 *   hamburger | AI search | #page-filters-target | FY year buttons | bell | activity
 *
 * Mode "page" (все остальные страницы):
 *   hamburger | #page-title-target ИЛИ route.meta.title | #page-filters-target | bell | activity
 *
 * Page-specific filters рендерятся через <Teleport to="#page-filters-target">
 * Page-specific custom title (если нужен динамический) через <Teleport to="#page-title-target">
 */
import {  inject, computed, ref, onMounted, onBeforeUnmount } from "vue";
import { useRoute } from "vue-router";
import { usePortfolioYearStore } from "@/stores/portfolioYear";

const route = useRoute();
const yearStore = usePortfolioYearStore();
const toggleSidebar = inject<() => void>("toggleSidebar", () => {});
const openMobileSidebar = inject<() => void>("openMobileSidebar", () => {});
// На планшете/мобильном (≤1023px, где сайдбар off-canvas) бургер открывает
// сайдбар; на десктопе — сворачивает/разворачивает.
function onBurger() {
  if (typeof window !== "undefined" && window.innerWidth <= 1023) openMobileSidebar();
  else toggleSidebar();
}

const isDashboard = computed(() => route.path === "/dashboard");


const yearMenuOpen = ref(false);
function toggleYearMenu() { yearMenuOpen.value = !yearMenuOpen.value; }
function closeYearMenu() { yearMenuOpen.value = false; }

// Закрытие при клике вне dropdown
function onDocClick(e: MouseEvent) {
  const target = e.target as HTMLElement;
  if (!target.closest('.apt-year-dd')) {
    yearMenuOpen.value = false;
  }
}
onMounted(() => document.addEventListener('click', onDocClick));
onBeforeUnmount(() => document.removeEventListener('click', onDocClick));
const yearButtons = computed(() => {
  const ys = yearStore.availableYears;
  if (ys && ys.length) return ys;
  return [2026, 2025];
});
</script>

<template>
  <!-- ═══ MODE: DASHBOARD (full version) ═══ -->
  <header v-if="isDashboard" class="apt-bar apt-bar--dashboard">
    <button class="apt-burger" @click="onBurger()" title="Меню / свернуть сайдбар">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
        <line x1="3" y1="6" x2="21" y2="6"/>
        <line x1="3" y1="12" x2="21" y2="12"/>
        <line x1="3" y1="18" x2="21" y2="18"/>
      </svg>
    </button>

    <!-- Page title (из route.meta.title или teleport-таргет) -->
    <div class="apt-title">
      <div id="page-title-target" class="apt-title-slot"></div>
      <span class="apt-title-fallback">{{ route.meta.title || '' }}</span>
    </div>

    <!-- Flex spacer — прижимает фильтры/год к правому краю -->
    <div class="apt-spacer"></div>
    <div id="page-filters-target" class="apt-filters"></div>

    <div class="apt-year-dd" v-if="yearButtons.length" :class="{ open: yearMenuOpen }">
      <button class="apt-year-dd-btn" @click.stop="toggleYearMenu" type="button">
        FY {{ yearStore.year }}
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
      </button>
      <div class="apt-year-dd-menu" v-show="yearMenuOpen">
        <button v-for="y in yearButtons"
                :key="y"
                :class="{ on: yearStore.year === y }"
                @click="yearStore.setYear(y); closeYearMenu()"
                type="button">
          FY {{ y }}
        </button>
      </div>
    </div>

  </header>
</template>

<style scoped>
.apt-title {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  flex-shrink: 1;
}
.apt-title-slot {
  display: inline-flex;
  align-items: center;
}
.apt-title-slot:not(:empty) + .apt-title-fallback { display: none; }
.apt-title-fallback {
  font-size: 15px;
  font-weight: 700;
  color: rgba(255, 255, 255, 0.95);
  letter-spacing: -0.03em;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.apt-spacer { flex: 1 1 auto; min-width: 8px; }

.apt-bar {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: clamp(10px, 1vw, 14px) clamp(12px, 1.2vw, 18px);
  /* Та же вертикальная шкала, что у сайдбара (.uza-aside, 180deg на всю
     высоту вьюпорта) — топбар сэмплит верхние 56px того же градиента, поэтому
     цвет точно совпадает с примыкающим сайдбаром на стыке. */
  background: linear-gradient(180deg, #0C1230 0%, #111A3E 100%);
  background-size: 100% 100dvh;   /* dvh — согласовано с body/#app/сайдбаром, без шва */
  background-repeat: no-repeat;
  flex-wrap: wrap;
  row-gap: 8px;
  border-bottom: 0.5px solid rgba(255, 255, 255, 0.06);
}

.apt-burger {
  width: 34px;
  height: 34px;
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.08);
  color: rgba(255, 255, 255, 0.85);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: background 0.15s ease, border-color 0.15s ease, transform 0.16s ease;
}
.apt-burger:hover {
  background: rgba(255, 255, 255, 0.14);
  border-color: rgba(255, 255, 255, 0.22);
  color: #fff;
}
.apt-burger:active { transform: scale(0.94); }

/* === Dashboard mode === */
.apt-search {
  flex: 1;
  min-width: 240px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  background: rgba(255, 255, 255, 0.06);
  border: 0.5px solid rgba(255, 255, 255, 0.1);
  border-radius: 9px;
}
.apt-search-icon { color: rgba(255, 255, 255, 0.55); display: inline-flex; }
.apt-ai-badge {
  font-size: 9.5px;
  font-weight: 600;
  letter-spacing: 0.05em;
  background: linear-gradient(135deg, #7F77DD 0%, var(--blue) 100%);
  color: #fff;
  padding: 2px 6px;
  border-radius: 4px;
}
.apt-search-input {
  flex: 1;
  background: transparent;
  border: none;
  outline: none;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.85);
}
.apt-search-input::placeholder { color: rgba(255, 255, 255, 0.4); }


/* === Shared === */
.apt-filters {
  display: flex;
  align-items: center;
  gap: 7px;
  flex-wrap: wrap;
}
.apt-filters:empty { display: none; }

/* Year dropdown — в стиле ExecDashFinanceBlock */
.apt-year-dd { position: relative; }
.apt-year-dd.open .apt-year-dd-btn svg { transform: rotate(180deg); }
.apt-year-dd-btn {
  display: inline-flex; align-items: center; gap: 6px;
  background: rgba(239, 159, 39, 0.14);
  border: 0.5px solid rgba(239, 159, 39, 0.32);
  border-radius: 8px;
  font-size: 11px; font-weight: 600; letter-spacing: 0.04em;
  color: #FFE3B8;
  padding: 5px 11px;
  cursor: pointer;
  font-family: inherit;
  font-feature-settings: "tnum";
  transition: background 0.15s ease, border-color 0.15s ease;
}
.apt-year-dd-btn:hover {
  background: rgba(239, 159, 39, 0.20);
  border-color: rgba(239, 159, 39, 0.45);
}
.apt-year-dd-btn svg { color: rgba(255, 227, 184, 0.7); transition: transform 0.2s ease; }
.apt-year-dd-menu {
  display: flex;
  position: absolute;
  top: calc(100% + 4px); right: 0;
  background: var(--bg1, #fff);
  border: 0.5px solid rgba(15, 23, 60, 0.10);
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(15, 23, 60, 0.18);
  padding: 4px;
  flex-direction: column;
  min-width: 100px;
  z-index: var(--z-dropdown, 900);
}
.apt-year-dd-menu button {
  background: transparent;
  border: none;
  text-align: left;
  font-size: 11px;
  font-weight: 600;
  color: var(--t1, #1E2A4A);
  padding: 6px 12px;
  border-radius: 5px;
  cursor: pointer;
  font-family: inherit;
}
.apt-year-dd-menu button:hover { background: rgba(127, 119, 221, 0.08); }
.apt-year-dd-menu button.on { background: rgba(239, 159, 39, 0.16); color: #C97A0F; }
</style>