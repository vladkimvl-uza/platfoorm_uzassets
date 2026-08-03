<script setup lang="ts">
/**
 * Переключатель языка интерфейса — дропдаун по канону чипов платформы.
 *
 * Локали: ru / uz-latn / uz-cyr / en (реестр APP_LOCALES). Выбор хранится в
 * Pinia-сторе locale (localStorage) и мгновенно перерисовывает все строки,
 * прошедшие через t(), и все числа/даты через useFormatters.
 *
 * variant="dark"  — для тёмного сайдбара/топбара (по умолчанию);
 * variant="light" — для светлых поверхностей (страница логина).
 */
import { onBeforeUnmount, onMounted, ref } from "vue";

import flagGb from "@/assets/flags/gb.svg";
import flagRu from "@/assets/flags/ru.svg";
import flagUz from "@/assets/flags/uz.svg";
import {
  APP_LOCALES,
  LOCALE_NAME,
  LOCALE_SHORT,
  type AppLocale,
} from "@/locale/locales";
import { useLocaleStore } from "@/stores/locale";
import { useI18n } from "@/composables/useI18n";
const { t } = useI18n();


withDefaults(defineProps<{ variant?: "dark" | "light" }>(), { variant: "dark" });

const store = useLocaleStore();
const open = ref(false);
// Куда раскрывать список. Меню было жёстко привязано вверх (сделано под подвал
// сайдбара) — в топбаре /home оно уходило за край экрана и было не видно.
// Решаем при открытии: если сверху места нет, а снизу есть — раскрываем вниз.
const rootEl = ref<HTMLElement | null>(null);
const MENU_H = 190;   // высота меню из четырёх пунктов с отступами
const MENU_W = 176;

// Меню выносим в <body> и позиционируем фиксированно. Раньше оно было
// absolute внутри переключателя: на /home топбар и баннер создают свои
// контексты наложения (z-index + overflow: hidden), и меню либо обрезалось,
// либо перехват кликов уходил соседнему элементу — выбрать язык было нельзя.
const menuPos = ref<{ top: number; left: number }>({ top: 0, left: 0 });

function place() {
  const r = rootEl.value?.getBoundingClientRect();
  if (!r) return;
  const spaceBelow = window.innerHeight - r.bottom;
  const up = spaceBelow < MENU_H && r.top >= MENU_H;
  menuPos.value = {
    top: up ? Math.max(8, r.top - MENU_H - 6) : r.bottom + 6,
    // не даём уехать за правый край экрана
    left: Math.min(Math.max(8, r.left), window.innerWidth - MENU_W - 8),
  };
}

function toggle() {
  if (!open.value) place();
  open.value = !open.value;
}
function onViewportChange() {
  if (open.value) place();
}
const localeFlag: Record<AppLocale, string> = {
  ru: flagRu,
  "uz-latn": flagUz,
  "uz-cyr": flagUz,
  en: flagGb,
};

function pick(loc: AppLocale) {
  store.set(loc);
  open.value = false;
}

function onDocClick(e: MouseEvent) {
  const el = e.target as HTMLElement;
  // Меню телепортировано в body, поэтому проверяем и его собственный класс.
  if (!el.closest(".lsw-root") && !el.closest(".lsw-menu")) open.value = false;
}
onMounted(() => {
  document.addEventListener("click", onDocClick);
  window.addEventListener("resize", onViewportChange);
  window.addEventListener("scroll", onViewportChange, true);
});
onBeforeUnmount(() => {
  document.removeEventListener("click", onDocClick);
  window.removeEventListener("resize", onViewportChange);
  window.removeEventListener("scroll", onViewportChange, true);
});
</script>

<template>
  <div ref="rootEl" class="lsw-root" :class="`lsw-${variant}`">
    <button
      class="lsw-btn"
      type="button"
      :title="LOCALE_NAME[store.current]"
      :aria-label="t('Til / Язык / Language: {value0}', { value0: LOCALE_NAME[store.current] })"
      @click.stop="toggle"
    >
      <img class="lsw-flag" :src="localeFlag[store.current]" alt="" aria-hidden="true" />
      <span class="lsw-code">{{ LOCALE_SHORT[store.current] }}</span>
      <svg class="lsw-chev" :class="{ open }" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9" /></svg>
    </button>

    <Teleport to="body">
      <div v-show="open" class="lsw-menu" :class="`lsw-${variant}`" role="listbox"
           :style="{ top: menuPos.top + 'px', left: menuPos.left + 'px' }">
      <button
        v-for="loc in APP_LOCALES"
        :key="loc"
        type="button"
        role="option"
        :aria-selected="store.current === loc"
        :class="{ on: store.current === loc }"
        @click="pick(loc)"
      >
        <img class="lsw-menu-flag" :src="localeFlag[loc]" alt="" aria-hidden="true" />
        <span class="lsw-mcode">{{ LOCALE_SHORT[loc] }}</span>
        <span>{{ LOCALE_NAME[loc] }}</span>
        </button>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.lsw-root { position: relative; display: inline-flex; }

.lsw-btn {
  display: inline-flex; align-items: center; gap: 5px;
  border-radius: 8px;
  font-size: 10.5px; font-weight: 600; letter-spacing: 0.04em;
  padding: 5px 9px;
  cursor: pointer;
  font-family: inherit;
  transition: background 0.15s ease, border-color 0.15s ease;
}
.lsw-flag,
.lsw-menu-flag {
  display: block;
  object-fit: cover;
  flex: 0 0 auto;
  border-radius: 2px;
  box-shadow: 0 0 0 0.5px rgba(15, 23, 60, 0.24);
}
.lsw-flag { width: 15px; height: 10px; }
.lsw-menu-flag { width: 18px; height: 12px; }
.lsw-dark .lsw-flag { box-shadow: 0 0 0 0.5px rgba(255, 255, 255, 0.28); }
.lsw-dark .lsw-btn {
  background: rgba(255, 255, 255, 0.07);
  border: 0.5px solid rgba(255, 255, 255, 0.14);
  color: rgba(255, 255, 255, 0.85);
}
.lsw-dark .lsw-btn:hover {
  background: rgba(255, 255, 255, 0.13);
  border-color: rgba(255, 255, 255, 0.24);
  color: #fff;
}
.lsw-light .lsw-btn {
  background: rgba(15, 23, 60, 0.04);
  border: 0.5px solid rgba(15, 23, 60, 0.12);
  color: var(--t1, #1e2a4a);
}
.lsw-light .lsw-btn:hover {
  background: rgba(15, 23, 60, 0.08);
  border-color: rgba(15, 23, 60, 0.2);
}
.lsw-chev { transition: transform 0.2s ease; opacity: 0.7; }
.lsw-chev.open { transform: rotate(180deg); }

.lsw-menu {
  position: fixed;
  display: flex; flex-direction: column;
  background: var(--bg1, #fff);
  border: 0.5px solid rgba(15, 23, 60, 0.1);
  border-radius: 10px;
  box-shadow: 0 10px 28px rgba(15, 23, 60, 0.2);
  padding: 4px;
  min-width: 168px;
  z-index: var(--z-toast, 9800);
}
.lsw-menu button {
  display: flex; align-items: center; gap: 8px;
  background: transparent; border: none;
  text-align: left;
  font-size: 12px; font-weight: 500;
  color: var(--t1, #1e2a4a);
  padding: 7px 10px;
  border-radius: 6px;
  cursor: pointer;
  font-family: inherit;
}
.lsw-menu button:hover { background: rgba(127, 119, 221, 0.08); }
.lsw-menu button.on { background: rgba(127, 119, 221, 0.14); color: var(--p-deep, #534ab7); font-weight: 600; }
.lsw-mcode {
  font-size: 9.5px; font-weight: 700; letter-spacing: 0.05em;
  color: rgba(15, 23, 60, 0.45);
  min-width: 22px;
}
.lsw-menu button.on .lsw-mcode { color: var(--p-deep, #534ab7); }
</style>
