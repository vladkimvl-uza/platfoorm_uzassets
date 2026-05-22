/**
 * useCountUp — premium count-up animation for KPI numbers.
 *
 * Usage:
 *   <span ref="el">{{ display }}</span>
 *   const { display, animate } = useCountUp(940, { duration: 900 });
 *   onMounted(() => animate());  // or watch a value and re-animate on change
 *
 * Why not pure CSS @property:
 *   @property --uza-num works only for integers in modern browsers and can't
 *   format thousands separators. JS keeps formatting flexibility.
 *
 * Performance: requestAnimationFrame with cubic-bezier easing. ~60fps.
 */
import { ref, watch, type Ref } from "vue";

export { runCountUp as countUpScan } from "@/utils/countUp";

export interface CountUpOptions {
  /** Animation duration in ms. Default 900. */
  duration?: number;
  /** Easing function: 'easeOut' | 'easeSoft' | 'linear'. Default 'easeSoft'. */
  easing?: "easeOut" | "easeSoft" | "linear";
  /** Decimals to keep. Default 0. */
  decimals?: number;
  /** Locale for thousand separators. Default 'ru-RU'. */
  locale?: string;
  /** Suffix appended to formatted number (e.g. "%", "млрд"). Default ''. */
  suffix?: string;
}

const EASINGS = {
  // Apple-style: cubic-bezier(.22, 1, .36, 1)
  easeOut: (t: number): number => 1 - Math.pow(1 - t, 3),
  // Spring-like soft: cubic-bezier(0.34, 1.2, 0.64, 1) — slight overshoot
  easeSoft: (t: number): number => {
    const c1 = 1.70158;
    const c3 = c1 + 1;
    return 1 + c3 * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2);
  },
  linear: (t: number): number => t,
};

/**
 * Animates from a starting value to a target value, exposing a formatted
 * `display` string ref. Pass a Ref<number> for `target` to auto-reanimate
 * on changes. Pass a number to animate once.
 */
export function useCountUp(
  target: number | Ref<number>,
  options: CountUpOptions = {},
) {
  const {
    duration = 900,
    easing = "easeSoft",
    decimals = 0,
    locale = "ru-RU",
    suffix = "",
  } = options;

  const current = ref<number>(0);
  const display = ref<string>(format(0));

  function format(v: number): string {
    if (!isFinite(v) || isNaN(v)) return "—";
    const fmt = v.toLocaleString(locale, {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    });
    return suffix ? `${fmt}${suffix}` : fmt;
  }

  let frame = 0;

  function animateTo(from: number, to: number): void {
    if (frame) cancelAnimationFrame(frame);
    if (Math.abs(to - from) < .5 && decimals === 0) {
      current.value = to;
      display.value = format(to);
      return;
    }
    // Respect reduced-motion preference
    if (typeof window !== "undefined" && window.matchMedia) {
      const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
      if (mq.matches) {
        current.value = to;
        display.value = format(to);
        return;
      }
    }
    const start = performance.now();
    const easer = EASINGS[easing] || EASINGS.easeSoft;
    const step = (now: number) => {
      const t = Math.min(1, (now - start) / duration);
      const eased = easer(t);
      const v = from + (to - from) * eased;
      current.value = v;
      display.value = format(v);
      if (t < 1) frame = requestAnimationFrame(step);
      else frame = 0;
    };
    frame = requestAnimationFrame(step);
  }

  function getTargetValue(): number {
    if (typeof target === "number") return target;
    return (target as Ref<number>).value || 0;
  }

  function animate(): void {
    animateTo(current.value, getTargetValue());
  }

  if (typeof target !== "number") {
    watch(target as Ref<number>, (newVal, oldVal) => {
      animateTo(oldVal || 0, newVal || 0);
    });
  }

  return { display, current, animate };
}


/**
 *
 * Scans a container element for all `[data-countup]` descendants and animates
 * (`document.querySelectorAll('[data-countup]')` → `_countUpEl(e, val, 750, baseDelay + i*80)`).
 *
 * Usage:
 *   const bandRef = ref<HTMLElement | null>(null);
 *   useCountUpScan(bandRef, { baseDelay: 60 });
 *
 * Each scanned span needs:
 *   <span data-countup="123.45" data-cu-d="1" [data-cu-sep]></span>
 *
 * Re-scans automatically when DOM changes via MutationObserver (debounced 50ms).
 */
import { onMounted, onBeforeUnmount, nextTick } from "vue";

export interface CountUpScanOptions {
  /** Initial delay before stagger starts. Default 0. */
  baseDelay?: number;
  /** Per-element stagger increment in ms. Default 80. */
  stagger?: number;
  /** Animation duration. Default 750. */
  duration?: number;
  /** Re-scan on DOM mutations. Default true. */
  reactive?: boolean;
}

function _ease(t: number): number {
  // cubic-bezier(0.34, 1.2, 0.64, 1) — Apple soft spring
  const c1 = 1.70158, c3 = c1 + 1;
  return 1 + c3 * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2);
}

function _animateOne(el: HTMLElement, target: number, duration: number, delay: number): void {
  const dec = parseInt(el.getAttribute("data-cu-d") || "0", 10);
  const sep = el.hasAttribute("data-cu-sep");
  const suffix = el.getAttribute("data-cu-suffix") || "";

  // Respect reduced-motion
  if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) {
    const s = dec > 0 ? target.toFixed(dec) : Math.round(target).toString();
    el.innerHTML = (sep ? s.replace(/\B(?=(\d{3})+(?!\d))/g, " ") : s) + suffix;
    return;
  }

  const start = performance.now() + delay;
  const fromVal = 0;
  el.innerHTML = "0" + suffix;
  el.setAttribute("data-cu-done", "1");

  function frame(now: number) {
    if (now < start) { requestAnimationFrame(frame); return; }
    const t = Math.min((now - start) / duration, 1);
    const eased = _ease(t);
    const cur = fromVal + (target - fromVal) * eased;
    const neg = cur < 0;
    const a = Math.abs(cur);
    let s = dec > 0 ? a.toFixed(dec) : Math.round(a).toString();
    if (sep) {
      const p = s.split(".");
      p[0] = p[0].replace(/\B(?=(\d{3})+(?!\d))/g, " ");
      s = p.join(".");
    }
    el.innerHTML = (neg ? "\u2212" : "") + s + suffix;
    if (t < 1) requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
}

export function useCountUpScan(
  containerRef: Ref<HTMLElement | null | undefined>,
  options: CountUpScanOptions = {},
): { rescan: () => void } {
  const { baseDelay = 0, stagger = 80, duration = 750, reactive = true } = options;
  let observer: MutationObserver | null = null;
  let scanTimer: number | null = null;

  function scan(): void {
    const el = containerRef.value;
    if (!el) return;
    const targets = el.querySelectorAll<HTMLElement>("[data-countup]:not([data-cu-done])");
    targets.forEach((node, i) => {
      const raw = parseFloat(node.getAttribute("data-countup") || "0");
      if (isNaN(raw)) return;
      _animateOne(node, raw, duration, baseDelay + i * stagger);
    });
    // Stagger --kpi2-d for any .kpi2 children (top-bar animation cascade)
    el.querySelectorAll<HTMLElement>(".kpi2").forEach((card, i) => {
      if (!card.style.getPropertyValue("--kpi2-d")) {
        card.style.setProperty("--kpi2-d", `${i * 100}ms`);
      }
    });
  }

  function scheduleRescan(): void {
    if (scanTimer) window.clearTimeout(scanTimer);
    scanTimer = window.setTimeout(() => { scan(); scanTimer = null; }, 50);
  }

  function rescan(): void {
    // Force re-animation by clearing data-cu-done flags
    const el = containerRef.value;
    if (!el) return;
    el.querySelectorAll<HTMLElement>("[data-countup][data-cu-done]").forEach(n => {
      n.removeAttribute("data-cu-done");
    });
    scan();
  }

  onMounted(async () => {
    await nextTick();
    scan();
    if (reactive && containerRef.value) {
      observer = new MutationObserver(scheduleRescan);
      observer.observe(containerRef.value, { childList: true, subtree: true, attributes: true, attributeFilter: ["data-countup"] });
    }
  });

  onBeforeUnmount(() => {
    if (observer) observer.disconnect();
    if (scanTimer) window.clearTimeout(scanTimer);
  });

  return { rescan };
}
