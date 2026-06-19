// v-reveal — премиум scroll-reveal: элемент мягко проявляется (fade-up) при
// входе в вьюпорт. Стаггер задаётся значением-задержкой в мс: v-reveal="120".
// Уважает prefers-reduced-motion (тогда контент показывается мгновенно, без
// анимации). Один общий IntersectionObserver на всё приложение.
import type { Directive } from "vue";

function prefersReduced(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

let observer: IntersectionObserver | null = null;
const delayMap = new WeakMap<Element, number>();

function ensureObserver(): IntersectionObserver | null {
  if (observer || typeof IntersectionObserver === "undefined") return observer;
  observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        const el = entry.target as HTMLElement;
        const delay = delayMap.get(el) || 0;
        el.style.transitionDelay = `${delay}ms`;
        el.classList.add("reveal-in");
        observer!.unobserve(el);
        delayMap.delete(el);
      }
    },
    { threshold: 0.06, rootMargin: "0px 0px -7% 0px" },
  );
  return observer;
}

export const reveal: Directive<HTMLElement, number | undefined> = {
  mounted(el, binding) {
    // reduced-motion или нет IO → показываем сразу, без скрытия.
    if (prefersReduced()) {
      el.classList.add("reveal-in");
      return;
    }
    el.classList.add("reveal-init");
    delayMap.set(el, typeof binding.value === "number" ? binding.value : 0);
    const obs = ensureObserver();
    if (obs) obs.observe(el);
    else el.classList.add("reveal-in"); // SSR / старые браузеры — fallback
  },
  unmounted(el) {
    observer?.unobserve(el);
    delayMap.delete(el);
  },
};
