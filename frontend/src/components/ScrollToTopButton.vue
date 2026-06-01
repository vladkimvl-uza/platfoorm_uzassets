<script setup lang="ts">
/**
 * ScrollToTopButton.vue — Pack 7.25
 *
 * Глобальная плавающая кнопка «наверх» в правом нижнем углу.
 * Glass/frosted стиль (вариант B из выбора пользователя).
 *
 * IMPORTANT — Pack 7.25 fix:
 *   В этом приложении body { overflow: hidden } и реальный скролл живёт
 *   на `.uza-main` (см. assets/main.css `.uza-main { overflow-y: auto }`).
 *   Pack 7.24 слушал window.scrollY который всегда = 0 — кнопка никогда
 *   не появлялась. Теперь:
 *     - При монтировании компонент находит `.uza-main` (или ближайший
 *       прокручиваемый предок)
 *     - Слушатель scroll и scrollTo привязаны к этому элементу
 *     - Через 200ms делается повторная попытка если AppShell ещё не
 *       срендерился (page change race)
 *
 * Поведение:
 *   • Скрыта когда scrollTop < SHOW_THRESHOLD (400px)
 *   • При появлении плавно проявляется (fade + slide вверх)
 *   • Клик → scroll-host.scrollTo({ top: 0, behavior: 'smooth' })
 *   • Throttle через requestAnimationFrame
 *   • Position: fixed — над всем контентом
 */
import { ref, onMounted, onBeforeUnmount } from "vue";

const SHOW_THRESHOLD = 150; // px  // Pack 7.38: lowered from 400 to show on shorter pages

const isVisible = ref(false);
let rafId = 0;
let scrollHost: HTMLElement | Window = window;
let retryId = 0;

function getScrollTop(): number {
  if (scrollHost === window) {
    return window.scrollY || document.documentElement.scrollTop || 0;
  }
  return (scrollHost as HTMLElement).scrollTop;
}

function onScroll() {
  if (rafId) return;
  rafId = requestAnimationFrame(() => {
    isVisible.value = getScrollTop() > SHOW_THRESHOLD;
    rafId = 0;
  });
}

function scrollToTop() {
  const reduce =
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const behavior: ScrollBehavior = reduce ? "auto" : "smooth";

  if (scrollHost === window) {
    window.scrollTo({ top: 0, behavior });
  } else {
    (scrollHost as HTMLElement).scrollTo({ top: 0, behavior });
  }
}

function attachToHost() {
  // Find the real scroll container. In this app it's `.uza-main` (see
  // assets/main.css — body has overflow:hidden, .uza-main has overflow-y:auto)
  const mainEl = document.querySelector(".uza-main") as HTMLElement | null;

  if (mainEl) {
    if (scrollHost !== mainEl) {
      detach();
      scrollHost = mainEl;
      mainEl.addEventListener("scroll", onScroll, { passive: true });
    }
  } else {
    // Fallback: listen on window (handles routes outside AppShell, e.g. login)
    if (scrollHost !== window) {
      detach();
      scrollHost = window;
    }
    window.addEventListener("scroll", onScroll, { passive: true });
  }
  onScroll();
}

function detach() {
  if (scrollHost === window) {
    window.removeEventListener("scroll", onScroll);
  } else {
    (scrollHost as HTMLElement).removeEventListener("scroll", onScroll);
  }
}

let mutationObserver: MutationObserver | null = null;

onMounted(() => {
  attachToHost();
  // Retry once after a tick — AppShell may not be in DOM yet on first mount
  retryId = window.setTimeout(attachToHost, 200);

  // Also re-check on route navigation (hashchange / popstate as a cheap signal)
  window.addEventListener("popstate", attachToHost);

  // Pack 7.38: Vue Router uses pushState which doesn't fire popstate. If the
  // scroll container element is replaced on route change (or AppShell ever
  // remounts), the listener gets orphaned. MutationObserver on document.body
  // re-checks attachment on any DOM change — debounced via the scrollHost
  // identity check inside attachToHost(), so re-attach is a no-op when nothing
  // changed.
  if (typeof MutationObserver !== "undefined") {
    mutationObserver = new MutationObserver(() => {
      // Re-attach only if our current scrollHost is no longer in the document
      // (orphaned) or if .uza-main exists but we're still on window.
      const mainEl = document.querySelector(".uza-main") as HTMLElement | null;
      const hostOrphaned = scrollHost !== window
        && !document.body.contains(scrollHost as HTMLElement);
      const shouldSwitch = mainEl && scrollHost === window;
      if (hostOrphaned || shouldSwitch) attachToHost();
    });
    mutationObserver.observe(document.body, { childList: true, subtree: false });
  }
});

onBeforeUnmount(() => {
  detach();
  if (rafId) cancelAnimationFrame(rafId);
  if (retryId) clearTimeout(retryId);
  window.removeEventListener("popstate", attachToHost);
  if (mutationObserver) { mutationObserver.disconnect(); mutationObserver = null; }
});
</script>

<template>
  <transition name="uza-fade">
    <button
      v-if="isVisible"
      class="stt-btn"
      type="button"
      aria-label="Прокрутить наверх"
      title="Наверх"
      @click="scrollToTop"
    >
      <svg
        width="16"
        height="16"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2.4"
        stroke-linecap="round"
        stroke-linejoin="round"
      >
        <polyline points="6 14 12 8 18 14" />
      </svg>
    </button>
  </transition>
</template>

<style scoped>
.stt-btn {
  position: fixed;
  right: 24px;
  bottom: 24px;
  z-index: 2000;  /* Pack 7.38: raised so chat widgets / tooltips / etc don't cover it */

  width: 44px;
  height: 44px;
  border-radius: 50%;

  background: rgba(255, 255, 255, 0.85);
  backdrop-filter: blur(10px) saturate(1.4);
  -webkit-backdrop-filter: blur(10px) saturate(1.4);
  color: #5B54B8;

  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;

  border: 1px solid rgba(127, 119, 221, 0.25);
  box-shadow:
    0 4px 14px rgba(15, 23, 60, 0.10),
    0 1px 3px rgba(15, 23, 60, 0.05);

  transition: background 0.2s, border-color 0.2s, transform 0.2s, box-shadow 0.2s;
  font-family: inherit;
  padding: 0;
}
.stt-btn:hover {
  background: rgba(127, 119, 221, 0.12);
  border-color: rgba(127, 119, 221, 0.5);
  transform: translateY(-2px);
  box-shadow:
    0 8px 22px rgba(127, 119, 221, 0.20),
    0 2px 6px rgba(15, 23, 60, 0.08);
}
.stt-btn:active {
  transform: translateY(0);
  transition-duration: 0.06s;
}
.stt-btn:focus-visible {
  outline: 2px solid #7F77DD;
  outline-offset: 2px;
}

.stt-fade-enter-active,
.stt-fade-leave-active {
  transition: opacity 0.28s ease, transform 0.28s var(--ease-standard);
}
.stt-fade-enter-from {
  opacity: 0;
  transform: translateY(12px) scale(0.92);
}
.stt-fade-leave-to {
  opacity: 0;
  transform: translateY(12px) scale(0.92);
}

@media (max-width: 640px) {
  .stt-btn {
    right: 16px;
    bottom: 16px;
    width: 40px;
    height: 40px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .stt-btn,
  .stt-fade-enter-active,
  .stt-fade-leave-active {
    transition-duration: 0.05s;
  }
}
</style>
