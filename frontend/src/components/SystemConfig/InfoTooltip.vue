<script setup lang="ts">
/**
 * InfoTooltip.vue — Pack 7.40
 * ─────────────────────────────────────────────────────────────────
 * Маленькая иконка «?» которая по hover/focus открывает тёмную плашку
 * с подсказкой максимально простыми словами.
 *
 * Использование:
 *   <InfoTooltip>
 *     <strong>Инфляция %</strong><br>
 *     На сколько в среднем выросли цены за год. Например, если 10%
 *     — товар который стоил 100 сум, теперь стоит 110.
 *   </InfoTooltip>
 *
 * Слот `default` принимает любой HTML (можно <strong>, <br>, <code>).
 *
 * Props:
 *   • placement — "bottom" (default) | "top" | "right"
 *   • align     — "left" (default) | "center" | "right"
 *   • width     — макс. ширина плашки в px (default 280)
 */
import { ref, computed } from "vue";

const props = withDefaults(
  defineProps<{
    placement?: "bottom" | "top" | "right";
    align?: "left" | "center" | "right";
    width?: number;
    iconSize?: number;
  }>(),
  {
    placement: "bottom",
    align: "left",
    width: 280,
    iconSize: 14,
  },
);

const isOpen = ref(false);
const triggerRef = ref<HTMLElement | null>(null);

function show() {
  isOpen.value = true;
}
function hide() {
  isOpen.value = false;
}
function toggle() {
  isOpen.value = !isOpen.value;
}

const popStyle = computed(() => {
  const w = `${props.width}px`;
  // Позиционирование: по placement и align
  const base: Record<string, string> = {
    "max-width": w,
    "min-width": "180px",
  };
  if (props.placement === "bottom") {
    base.top = "calc(100% + 8px)";
    base.bottom = "auto";
  } else if (props.placement === "top") {
    base.bottom = "calc(100% + 8px)";
    base.top = "auto";
  } else if (props.placement === "right") {
    base.left = "calc(100% + 8px)";
    base.top = "0";
  }
  if (props.placement !== "right") {
    if (props.align === "left") base.left = "-4px";
    else if (props.align === "right") base.right = "-4px";
    else {
      base.left = "50%";
      base.transform = "translateX(-50%)";
    }
  }
  return base;
});

const arrowStyle = computed(() => {
  const base: Record<string, string> = {};
  if (props.placement === "bottom") {
    base.top = "-4px";
    if (props.align === "left") base.left = "12px";
    else if (props.align === "right") base.right = "12px";
    else base.left = "calc(50% - 4px)";
  } else if (props.placement === "top") {
    base.bottom = "-4px";
    if (props.align === "left") base.left = "12px";
    else if (props.align === "right") base.right = "12px";
    else base.left = "calc(50% - 4px)";
  } else if (props.placement === "right") {
    base.left = "-4px";
    base.top = "14px";
  }
  return base;
});
</script>

<template>
  <span
    ref="triggerRef"
    class="it-anchor"
    @mouseenter="show"
    @mouseleave="hide"
    @focusin="show"
    @focusout="hide"
    @click.stop="toggle"
  >
    <span
      class="it-icon"
      :style="{ width: `${iconSize}px`, height: `${iconSize}px`, fontSize: `${Math.round(iconSize * 0.62)}px` }"
      role="button"
      tabindex="0"
      aria-label="Показать подсказку"
    >
      ?
    </span>

    <Transition name="uza-fade">
      <span
        v-if="isOpen"
        class="it-pop"
        :class="`it-pop--${placement}`"
        :style="popStyle"
        role="tooltip"
      >
        <span class="it-arrow" :style="arrowStyle"></span>
        <slot />
      </span>
    </Transition>
  </span>
</template>

<style scoped>
.it-anchor {
  position: relative;
  display: inline-flex;
  align-items: center;
  vertical-align: middle;
  margin: 0 2px;
  cursor: help;
}

.it-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: rgba(127, 119, 221, 0.10);
  color: #534AB7;
  font-weight: 500;
  font-family: inherit;
  user-select: none;
  transition: background 0.14s, color 0.14s, transform 0.14s;
  outline: none;
}
.it-anchor:hover .it-icon,
.it-anchor:focus-within .it-icon {
  background: #534AB7;
  color: #fff;
  transform: scale(1.08);
}

.it-pop {
  position: absolute;
  z-index: 1000;
  background: #1E2A4A;
  color: #F1EFE8;
  padding: 10px 13px;
  border-radius: 8px;
  font-size: 11px;
  line-height: 1.55;
  font-weight: 400;
  letter-spacing: 0;
  text-transform: none;
  text-align: left;
  white-space: normal;
  box-shadow:
    0 8px 24px rgba(15, 23, 60, 0.20),
    0 2px 8px rgba(15, 23, 60, 0.12);
  pointer-events: none;
}
.it-pop :deep(strong) {
  color: #fff;
  font-weight: 500;
  display: inline-block;
  margin-bottom: 2px;
}
.it-pop :deep(code) {
  background: rgba(255, 255, 255, 0.08);
  padding: 1px 5px;
  border-radius: 3px;
  font-family: ui-monospace, Menlo, Consolas, monospace;
  font-size: 10px;
  color: #FFD9A8;
}
.it-pop :deep(em) {
  font-style: normal;
  color: #B5D4F4;
}
.it-pop :deep(p) {
  margin: 6px 0 0;
}
.it-pop :deep(p:first-child) {
  margin-top: 0;
}

.it-arrow {
  position: absolute;
  width: 8px;
  height: 8px;
  background: #1E2A4A;
  transform: rotate(45deg);
}

/* Transition */
.it-fade-enter-active,
.it-fade-leave-active {
  transition: opacity 0.18s ease, transform 0.22s cubic-bezier(0.34, 1.2, 0.64, 1);
}
.it-fade-enter-from {
  opacity: 0;
  transform: translateY(-4px) scale(0.96);
}
.it-pop--top.it-fade-enter-from {
  transform: translateY(4px) scale(0.96);
}
.it-fade-leave-to {
  opacity: 0;
  transform: scale(0.96);
}
</style>
