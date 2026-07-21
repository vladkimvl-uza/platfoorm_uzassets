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
    // embedded: тот же контент, но в потоке страницы (без оверлея/телепорта/
    // крестика/скролл-лока) — чтобы drill встраивался во вкладку воркспейса 1:1.
    embedded?: boolean;
  }>(),
  { accent: "#7F77DD", maxWidth: 820, stripe: "top", align: "center", embedded: false },
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
  if (props.embedded) return;   // встроенный режим — без блокировки скролла/Esc
  prevOverflow = document.body.style.overflow;
  document.body.style.overflow = "hidden";
  window.addEventListener("keydown", onKey);
});
onBeforeUnmount(() => {
  if (props.embedded) return;
  document.body.style.overflow = prevOverflow;
  window.removeEventListener("keydown", onKey);
});
</script>

<template>
  <!-- Встроенный режим: тело в потоке страницы, без модального chrome -->
  <div v-if="embedded" class="eds-embed" :style="{ '--sc': accent }">
    <slot />
  </div>

  <!-- Модальный режим (по умолчанию) -->
  <Teleport v-else to="body">
    <Transition name="eds-fade">
      <div class="eds-bd" :class="`eds-al-${align}`" @click="onBackdrop" role="dialog" aria-modal="true">
        <div
          ref="cardEl"
          tabindex="-1"
          class="eds-card"
          :style="{ '--sc': accent, maxWidth: maxWidth + 'px' }"
        >
          <button class="eds-x" type="button" @click="emit('close')" aria-label="Закрыть">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor"
                 stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
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

/* Встроенный режим — карточка в потоке страницы (тень мягче, без анимации входа) */
.eds-embed {
  position: relative;
  background: var(--bg1, #fff);
  border-radius: 16px;
  border: 0.5px solid var(--uza-border, #ECEAF5);
  box-shadow: 0 2px 10px rgba(15, 23, 60, 0.05);
  overflow: hidden;
}

.eds-card {
  position: relative;
  background: var(--bg1, #fff);
  border-radius: 16px;
  box-shadow: 0 24px 64px rgba(15, 23, 60, 0.18), 0 8px 24px rgba(15, 23, 60, 0.08);
  width: 100%;
  overflow: hidden;
  animation: edsIn 0.45s var(--ease-standard, cubic-bezier(.4, 0, .2, 1)) both;
}

.eds-x {
  position: absolute; top: 12px; right: 14px;
  width: 28px; height: 28px; border-radius: 6px;
  display: flex; align-items: center; justify-content: center;
  cursor: pointer; color: var(--t3, var(--t-muted));
  border: none; background: transparent;
  z-index: 6; transition: background 0.12s, color 0.12s;
}
.eds-x:hover { background: var(--bg3, #F1F5F9); color: var(--t1, #1E2A4A); }

.eds-fade-enter-active, .eds-fade-leave-active { transition: opacity 0.25s ease; }
.eds-fade-enter-from, .eds-fade-leave-to { opacity: 0; }

@keyframes edsIn {
  0%   { opacity: 0; transform: translateY(20px) scale(0.95); }
  100% { opacity: 1; transform: translateY(0) scale(1); }
}

@media (prefers-reduced-motion: reduce) {
  .eds-card { animation: none; }
}
</style>
