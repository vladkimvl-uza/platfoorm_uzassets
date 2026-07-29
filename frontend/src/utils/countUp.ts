/**
 * CountUp animation — единый стандарт для всех KPI/счётчиков платформы.
 *
 * Портирован 1:1 из легасиа (functions _countUpEl + _countUpScan, lines
 * 48900-49016 of index.html). Поведение:
 *
 *   – Старт с 0 на первой анимации (а не с финального значения, чтобы
 *     избежать flash of final value до начала анимации)
 *   – Easing: ease-out exponential (1 - 2^(-10t)) — мягкое замедление
 *     к финальному значению. Длительность 750ms.
 *   – Stagger 80ms между соседними счётчиками — выраженная волна
 *   – Re-render morph: через `data-cu-key` запоминается предыдущее значение
 *     (window._cuPrevVals), при следующем render'е анимация начинается
 *     не с 0, а с прошлого числа — что нужно для year-switch / filter-change
 *   – Decimals: атрибут `data-cu-d="1"` управляет числом знаков после запятой
 *   – Thousand separator: атрибут `data-cu-sep` включает разделение тысяч пробелом
 *   – Reduced motion: prefers-reduced-motion → сразу финальное значение
 *
 * ИСПОЛЬЗОВАНИЕ:
 *
 *   import { vCountUp } from "@/utils/countUp";
 *
 *   // в template:
 *   <span v-count-up="940">0</span>
 *   <span v-count-up="{ value: 1234.56, decimals: 2, thousandSep: true }">0</span>
 *
 *   // или через метод после render-а (для случаев где нужен ручной контроль):
 *   import { runCountUp } from "@/utils/countUp";
 *   onMounted(() => runCountUp(rootEl.value));
 */
import type { Directive, DirectiveBinding } from "vue";
import { nextTick } from "vue";

interface CountUpOptions {
  value: number | string;
  decimals?: number;        // data-cu-d
  thousandSep?: boolean;    // data-cu-sep
  key?: string;             // data-cu-key (for cross-render morph)
  duration?: number;        // ms (default 750)
  delay?: number;           // ms (default 0)
}

declare global {
  interface Window {
    _cuPrevVals?: Record<string, number>;
  }
}

function isReducedMotion(): boolean {
  if (typeof window === "undefined") return false;
  return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches || false;
}

function _ease(t: number): number {
  return t >= 1 ? 1 : 1 - Math.pow(2, -10 * t);
}

/**
 * Animate a single element to its target value.
 * Mirrors legacy's _countUpEl (line 48904).
 */
export function countUpEl(
  el: HTMLElement,
  target: number | string,
  duration = 750,
  delay = 0,
  options: { decimals?: number; thousandSep?: boolean; cuKey?: string } = {},
): void {
  if (!el) return;

  const raw = parseFloat(String(target).replace(/[\s,\u2212]/g, "").replace("−", "-")) || 0;
  const dec = options.decimals ?? parseInt(el.getAttribute("data-cu-d") || "0", 10) ?? 0;
  const sep = options.thousandSep ?? el.hasAttribute("data-cu-sep");
  const cuKey = options.cuKey ?? el.getAttribute("data-cu-key") ?? null;

  // Suffix preservation — preserve any HTML/text after the number
  // (e.g. "<span>%</span>", " лет", " / 1200")
  let orig = el.innerHTML;
  const stripped = orig.replace(/<[^>]+>/g, "").trim();
  if (
    stripped === "\u2014" || stripped === "—" || stripped === "-" ||
    stripped === "н/д" || stripped === "\u2026" || stripped === "..." // i18n-exempt: localized non-numeric sentinel parser
  ) {
    orig = "";
    el.innerHTML = "";
  }
  const m = orig.match(/^(\s*[\u2212\-]?[\d.,\s\u00A0]*)([\s\S]*)$/);
  let suffix = m ? m[2] : "";
  if (suffix && /[\u2014—]/.test(suffix)) {
    suffix = suffix.replace(/[\u2014—]/g, "").trim();
  if (suffix && !suffix.match(/^[\s%a-zа-яё/]/i)) suffix = " " + suffix; // i18n-exempt: suffix script classifier
  }

  // Initial state setup with cross-render morph support
  if (!window._cuPrevVals) window._cuPrevVals = {};
  const isFirstAnim = !el.hasAttribute("data-cu-done");
  let fromVal: number;

  if (cuKey && window._cuPrevVals[cuKey] != null) {
    fromVal = window._cuPrevVals[cuKey];
    el.setAttribute("data-cu-done", "1");
  } else if (isFirstAnim) {
    fromVal = 0;
    // Hide target in DOM immediately to avoid flash of final value
    el.innerHTML = "0" + suffix;
    el.setAttribute("data-cu-done", "1");
  } else {
    const prevTxt = (el.textContent || "").trim();
    const prevRaw = parseFloat(prevTxt.replace(/[\s,\u2212]/g, "").replace("−", "-"));
    fromVal = !isNaN(prevRaw) && prevTxt !== "" ? prevRaw : 0;
  }

  if (cuKey) window._cuPrevVals[cuKey] = raw;

  const startTime = performance.now() + delay;

  // Reduced motion: skip animation, set final value
  if (isReducedMotion()) {
    const s0 = dec > 0 ? raw.toFixed(dec) : Math.round(raw).toString();
    let formatted = s0;
    if (sep) {
      const p0 = formatted.split(".");
      p0[0] = p0[0].replace(/\B(?=(\d{3})+(?!\d))/g, " ");
      formatted = p0.join(".");
    }
    const isNeg = raw < 0;
    el.innerHTML = (isNeg ? "\u2212" : "") + formatted.replace("-", "") + suffix;
    return;
  }

  const _fmt = (v: number, isNeg: boolean): string => {
    const a = Math.abs(v);
    let s = dec > 0 ? a.toFixed(dec) : Math.round(a).toString();
    if (sep) {
      const p = s.split(".");
      p[0] = p[0].replace(/\B(?=(\d{3})+(?!\d))/g, " ");
      s = p.join(".");
    }
    return (isNeg ? "\u2212" : "") + s;
  };

  function frame(now: number) {
    if (now < startTime) {
      requestAnimationFrame(frame);
      return;
    }
    const t = Math.min((now - startTime) / duration, 1);
    const eased = _ease(t);
    const cur = fromVal + (raw - fromVal) * eased;
    el.innerHTML = _fmt(cur, cur < 0) + suffix;
    if (t < 1) requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
}

/**
 * Scan a container for all `[data-countup]` elements and animate them
 * with staggered delay (80ms between siblings).
 * Mirrors legacy's _countUpScan (line 49004).
 */
export function runCountUp(container: HTMLElement | null, baseDelay = 0): void {
  if (!container) return;
  const reduced = isReducedMotion();
  const stagger = reduced ? 0 : 80;
  const dur = reduced ? 1 : 750;
  const els = container.querySelectorAll<HTMLElement>("[data-countup]");
  els.forEach((e, i) => {
    const val = e.getAttribute("data-countup") || "0";
    countUpEl(e, val, dur, baseDelay + i * stagger);
  });
}


/**
 * Vue directive — declarative count-up.
 *
 * Usage:
 *   <span v-count-up="940">0</span>
 *   <span v-count-up="{ value: 12.34, decimals: 2, thousandSep: true }">0</span>
 *   <span v-count-up="{ value: ratings.score, key: 'rating-' + co.code }">0</span>
 *
 * The directive:
 *   • mounts → starts animation from 0 to value
 *   • updates → re-animates from previous value to new value (cross-render morph)
 *   • supports a `key` option for tracking values across re-renders
 *
 * Children placeholder of "0" is shown until the animation starts —
 * any HTML inside the element AFTER the number is preserved as suffix.
 */

function resolveOptions(binding: DirectiveBinding<number | string | CountUpOptions>): CountUpOptions {
  const v = binding.value;
  if (v == null) return { value: 0 };
  if (typeof v === "number" || typeof v === "string") return { value: v };
  return v;
}

function applyAttrs(el: HTMLElement, opts: CountUpOptions) {
  if (opts.decimals != null) el.setAttribute("data-cu-d", String(opts.decimals));
  else el.removeAttribute("data-cu-d");
  if (opts.thousandSep) el.setAttribute("data-cu-sep", "");
  else el.removeAttribute("data-cu-sep");
  if (opts.key) el.setAttribute("data-cu-key", opts.key);
}

export const vCountUp: Directive<HTMLElement, number | string | CountUpOptions> = {
  mounted(el, binding) {
    const opts = resolveOptions(binding);
    applyAttrs(el, opts);
    el.setAttribute("data-countup", String(opts.value));
    // Show "0" immediately on mount (before animation starts), so users
    // never see the final value flash — they always see the count up.
    el.innerHTML = "0";
    // Stagger: order by sibling index in the parent for natural wave effect
    const siblings = el.parentElement?.querySelectorAll<HTMLElement>("[data-countup]");
    let staggerIdx = 0;
    if (siblings) {
      for (let i = 0; i < siblings.length; i++) {
        if (siblings[i] === el) { staggerIdx = i; break; }
      }
    }
    const delay = isReducedMotion() ? 0 : staggerIdx * 80;
    // Defer to nextTick so the "0" placeholder paints before animation starts.
    void nextTick(() => {
      countUpEl(el, opts.value, opts.duration ?? 750, opts.delay ?? delay, {
        decimals: opts.decimals,
        thousandSep: opts.thousandSep,
        cuKey: opts.key,
      });
    });
  },
  updated(el, binding) {
    const opts = resolveOptions(binding);
    const oldOpts = resolveOptions({ ...binding, value: binding.oldValue } as DirectiveBinding<number | string | CountUpOptions>);
    if (String(opts.value) === String(oldOpts.value)) return;
    applyAttrs(el, opts);
    el.setAttribute("data-countup", String(opts.value));
    void nextTick(() => {
      countUpEl(el, opts.value, opts.duration ?? 750, opts.delay ?? 0, {
        decimals: opts.decimals,
        thousandSep: opts.thousandSep,
        cuKey: opts.key,
      });
    });
  },
};
