<script setup lang="ts">
/**
 * EntityDrillShell — общий каркас drill-модалок сущности (компания и т.п.).
 *
 * Выделен из трёх почти одинаковых модалок (UZA/CompanyDrillModal,
 * Dashboard/CompanyTileDrillModal, Financials/CompanyDrilldown) — п.3 Apple-аудита:
 * «единый shell, контент у каждой свой». Берёт на себя весь повторяющийся chrome:
 *   • Teleport в body + Transition (fade оверлея)
 *   • затемнение + блюр, центрирование, скролл при переполнении
 *   • карточка со скруглением/тенью + входная анимация
 *   • акцент-полоса (сверху или слева), однократный блик, мягкое свечение
 *   • крестик закрытия, ESC, клик по фону, блокировка скролла body
 * Тело (шапка-идентичность, секции, футер) кладёт вызывающий через слот.
 *
 * Блик намеренно ОДНОКРАТНЫЙ (не infinite) — Apple deference, как и в п.5.
 */
import { onMounted, onBeforeUnmount, ref } from "vue";
import { useFocusTrap } from "@/composables/useFocusTrap";

const props = withDefaults(
  defineProps<{
    accent?: string;          // цвет полосы/свечения (--sc)
    maxWidth?: number;        // макс. ширина карточки, px
    stripe?: "top" | "left";  // позиция акцент-полосы
    align?: "center" | "start"; // вертикальное выравнивание карточки
  }>(),
  { accent: "#7F77DD", maxWidth: 820, stripe: "top", align: "center" },
);

const emit = defineEmits<{ close: [] }>();

// a11y: фокус-трап + возврат фокуса (Escape/скролл-лок — ниже)
const cardEl = ref<HTMLElement | null>(null);
useFocusTrap(cardEl);

function onBackdrop(e: MouseEvent) {
  if (e.target === e.currentTarget) emit("close");
}
function onKey(e: KeyboardEvent) {
  if (e.key === "Escape") { e.preventDefault(); emit("close"); }
}

let prevOverflow = "";
onMounted(() => {
  prevOverflow = document.body.style.overflow;
  document.body.style.overflow = "hidden";
  window.addEventListener("keydown", onKey);
});
onBeforeUnmount(() => {
  document.body.style.overflow = prevOverflow;
  window.removeEventListener("keydown", onKey);
});
</script>

<template>
  <Teleport to="body">
    <Transition name="eds-fade">
      <div class="eds-bd" :class="`eds-al-${align}`" @click="onBackdrop" role="dialog" aria-modal="true">
        <div
          ref="cardEl"
          tabindex="-1"
          class="eds-card"
          :class="`eds-st-${stripe}`"
          :style="{ '--sc': accent, maxWidth: maxWidth + 'px' }"
        >
          <div class="eds-stripe" aria-hidden="true" />
          <div class="eds-shim" aria-hidden="true" />
          <div class="eds-glow" aria-hidden="true" />

          <button class="eds-x" type="button" @click="emit('close')" aria-label="Закрыть">
            <svg viewBox="0 0 14 14" width="13" height="13" fill="none" stroke="currentColor"
                 stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">
              <path d="M3.5 3.5l7 7M10.5 3.5l-7 7" />
            </svg>
          </button>

          <slot />
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.eds-bd {
  position: fixed; inset: 0;
  background: rgba(15, 18, 40, 0.45);
  -webkit-backdrop-filter: blur(8px); backdrop-filter: blur(8px);
  z-index: var(--z-top, 9990);
  display: flex; justify-content: center;
  padding: 24px 16px; overflow-y: auto;
}
.eds-al-center { align-items: center; }
.eds-al-start  { align-items: flex-start; }

.eds-card {
  position: relative;
  background: var(--bg1, #fff);
  border: 1px solid var(--card-border, transparent);
  border-radius: 14px;
  box-shadow: 0 24px 64px rgba(15, 23, 60, 0.22), 0 8px 24px rgba(15, 23, 60, 0.10);
  width: 100%;
  overflow: hidden;
  animation: edsIn 0.55s var(--ease-standard) 0.08s both;
}

.eds-stripe { position: absolute; background: var(--sc); z-index: 3; }
.eds-st-top .eds-stripe {
  top: 0; left: 0; right: 0; height: 3px;
  transform-origin: left center;
  animation: edsStripe 0.75s var(--ease-standard) 0.2s both;
}
.eds-st-left .eds-stripe {
  top: 14px; bottom: 14px; left: 0; width: 4px; border-radius: 0 4px 4px 0;
}

/* Блик — ОДНОКРАТНЫЙ entrance-проход (не infinite: Apple deference) */
.eds-shim {
  position: absolute; top: 0; left: 0; right: 0; height: 3px;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.75), transparent);
  transform: translateX(-120%);
  animation: edsShim 1.6s ease-in-out 0.9s 1 both;
  pointer-events: none; z-index: 4;
}
.eds-st-left .eds-shim { display: none; }

.eds-glow {
  position: absolute; inset: 0;
  background: radial-gradient(circle at 92% -6%, var(--sc), transparent 42%);
  opacity: 0.07; pointer-events: none; z-index: 1;
}

.eds-x {
  position: absolute; top: 14px; right: 14px;
  width: 28px; height: 28px; border-radius: 8px;
  display: flex; align-items: center; justify-content: center;
  cursor: pointer; color: var(--t3, var(--t-muted));
  border: 1px solid rgba(0, 0, 0, 0.06); background: var(--bg1, #fff);
  z-index: 6; transition: all 0.14s;
}
.eds-x:hover { background: var(--bg2, #FAFAFC); color: var(--t1, #1E2A4A); }

.eds-fade-enter-active, .eds-fade-leave-active { transition: opacity 0.28s ease; }
.eds-fade-enter-from, .eds-fade-leave-to { opacity: 0; }

@keyframes edsIn {
  0%   { opacity: 0; transform: translateY(22px) scale(0.96); }
  100% { opacity: 1; transform: translateY(0) scale(1); }
}
@keyframes edsStripe { from { transform: scaleX(0); } to { transform: scaleX(1); } }
@keyframes edsShim {
  0%        { transform: translateX(-120%); }
  60%, 100% { transform: translateX(220%); }
}
</style>
