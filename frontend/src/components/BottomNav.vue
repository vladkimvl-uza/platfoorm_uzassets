<script setup lang="ts">
/**
 * BottomNav — постоянная нижняя навигация для телефонов (Phase 2 mobile).
 *
 * Показывается только на узких экранах (≤768px), даёт быстрый доступ к ключевым
 * разделам + кнопку «Меню», открывающую полный сайдбар-drawer. Premium navy в
 * языке сайдбара/топбара, учитывает safe-area (домашний индикатор iOS).
 */
import { computed } from "vue";
import { RouterLink, useRoute } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { useI18n } from "@/composables/useI18n";

const { t } = useI18n();
const emit = defineEmits<{ (e: "menu"): void }>();
const auth = useAuthStore();
const route = useRoute();

function can(code: string): boolean {
  return auth.isOwner || auth.hasPermission(code);
}

const items = computed(() =>
  [
    { to: "/dashboard", label: "Главная", icon: "home", show: true },
    { to: "/library/companies", label: "Компании", icon: "building", show: can("companies.view") },
    { to: "/projects", label: "Проекты", icon: "tasks", show: can("tasks.view") },
    { to: "/ai-chat", label: "ИИ", icon: "ai", show: can("ai.view") },
  ].filter((i) => i.show),
);

// Активный пункт — по началу пути (чтобы вложенные роуты подсвечивали родителя).
function isActive(to: string): boolean {
  if (to === "/dashboard") return route.path === "/dashboard" || route.path === "/home" || route.path === "/";
  return route.path.startsWith(to);
}
</script>

<template>
  <nav class="bnav">
    <RouterLink
      v-for="it in items"
      :key="it.to"
      :to="it.to"
      class="bnav-item"
      :class="{ active: isActive(it.to) }"
    >
      <span class="bnav-ico">
        <svg v-if="it.icon === 'home'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V21h14V9.5"/><path d="M9.5 21v-6h5v6"/></svg>
        <svg v-else-if="it.icon === 'building'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="3" width="16" height="18" rx="1.5"/><path d="M9 7h2M13 7h2M9 11h2M13 11h2M9 15h2M13 15h2"/><path d="M10 21v-3h4v3"/></svg>
        <svg v-else-if="it.icon === 'tasks'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M9 6h11M9 12h11M9 18h11"/><path d="m4 6 1 1 2-2M4 12l1 1 2-2M4 18l1 1 2-2"/></svg>
        <svg v-else-if="it.icon === 'ai'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v3M12 18v3M3 12h3M18 12h3"/><path d="m6.3 6.3 2 2M15.7 15.7l2 2M17.7 6.3l-2 2M8.3 15.7l-2 2"/><circle cx="12" cy="12" r="3.2"/></svg>
      </span>
      <span class="bnav-lbl">{{ t(it.label) }}</span>
    </RouterLink>

    <button class="bnav-item bnav-menu" @click="emit('menu')" type="button">
      <span class="bnav-ico">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"><path d="M4 7h16M4 12h16M4 17h16"/></svg>
      </span>
      <span class="bnav-lbl">{{ t("Меню") }}</span>
    </button>
  </nav>
</template>

<style scoped>
.bnav {
  display: none;
}
@media (max-width: 768px) {
  .bnav {
    display: flex;
    position: fixed;
    left: 0; right: 0; bottom: 0;
    z-index: 95;
    background: linear-gradient(180deg, #111A3E 0%, #0C1230 100%);
    border-top: 0.5px solid rgba(255, 255, 255, 0.08);
    box-shadow: 0 -8px 24px rgba(8, 11, 30, 0.35);
    padding-bottom: env(safe-area-inset-bottom);
  }
}

.bnav-item {
  flex: 1 1 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 3px;
  padding: 8px 2px 9px;
  min-height: 54px;
  text-decoration: none;
  background: transparent;
  border: none;
  cursor: pointer;
  font-family: inherit;
  color: rgba(255, 255, 255, 0.58);
  transition: color 0.16s ease;
  position: relative;
}
.bnav-item:active { color: #fff; }
.bnav-item.active { color: #fff; }
/* Подсветка активного — фиолетовая «капля» под иконкой */
.bnav-item.active::before {
  content: "";
  position: absolute;
  top: 6px;
  width: 34px; height: 30px;
  border-radius: 12px;
  background: radial-gradient(60% 70% at 50% 40%, rgba(127, 119, 221, 0.55), transparent 72%);
  z-index: 0;
}
.bnav-ico {
  width: 22px; height: 22px;
  display: flex; align-items: center; justify-content: center;
  position: relative; z-index: 1;
}
.bnav-ico svg { width: 22px; height: 22px; }
.bnav-item.active .bnav-ico { color: #B5AEEC; }
.bnav-lbl {
  font-size: 10px;
  font-weight: 500;
  letter-spacing: 0.01em;
  position: relative; z-index: 1;
}
</style>
