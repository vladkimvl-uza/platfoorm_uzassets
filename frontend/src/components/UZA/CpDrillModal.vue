<template>
  <Teleport to="body">
    <div
      class="cp-drill-bg"
      :class="{ closing: isClosing }"
      @click.self="requestClose"
    >
      <div
        ref="cardRef"
        class="cp-drill-card"
        :class="`size-${size}`"
        :style="{ '--cd-accent': accent, '--cd-bg': accentBg }"
      >
        <!-- Header -->
        <div class="cp-drill-h">
          <div class="cp-drill-icn" v-html="iconHtml" />
          <div class="cp-drill-h-text">
            <div class="cp-drill-t">{{ title }}</div>
            <div v-if="subtitle" class="cp-drill-s">{{ subtitle }}</div>
          </div>
          <button class="cp-drill-x" @click="requestClose" aria-label="Закрыть">×</button>
        </div>

        <!-- Body -->
        <div class="cp-drill-body">
          <!-- Hero: data-driven OR slot -->
          <div v-if="hero || $slots.hero" class="cp-drill-hero">
            <slot name="hero">
              <template v-if="hero">
                <div class="cp-drill-hero-numwrap">
                  <span
                    class="cp-drill-hero-num"
                    :data-countup="hero.value"
                    :data-cu-d="hero.cuDecimals ?? 0"
                  >
                    {{ hero.value }}
                  </span>
                  <span v-if="hero.unit" class="cp-drill-hero-unit">{{ hero.unit }}</span>
                </div>
                <div class="cp-drill-hero-meta">
                  <div v-if="hero.label" class="cp-drill-hero-lbl">{{ hero.label }}</div>
                  <div v-if="hero.sub" class="cp-drill-hero-sub">{{ hero.sub }}</div>
                </div>
              </template>
            </slot>
          </div>

          <!-- Sections -->
          <div
            v-for="(sec, i) in sections"
            :key="i"
            class="cp-drill-sec"
            :style="{ '--cd-d': `${sec.delay ?? i * 80}ms` }"
          >
            <div v-if="sec.title" class="cp-drill-sec-h">
              <span>{{ sec.title }}</span>
              <span v-if="sec.count != null" class="cp-drill-sec-cnt">· {{ sec.count }}</span>
            </div>
            <div v-html="sec.body" />
          </div>

          <!-- Default slot for fully-custom content -->
          <slot />
        </div>

        <!-- Footer -->
        <div v-if="footer || $slots.footer" class="cp-drill-foot">
          <slot name="footer">
            <span v-if="footer" v-html="footer" />
          </slot>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
/**
 * CpDrillModal — 1:1 port of legacy `cpDrillOpen()` factory (line 27911 of index.html).
 *
 * Provides hero/sections/footer slots OR data-driven props for parity with the
 * legacy helpers `cpDrillHeroHtml`, `cpDrillStatGridHtml`, `cpDrillBarsHtml`.
 *
 * Behaviour:
 *   - Backdrop click closes (unless on the card itself)
 *   - ESC key closes
 *   - .closing class for 250ms exit animation
 *   - Triggers `useCountUpScan` on the card after 100ms (matches legacy setTimeout(100))
 *   - Sections fade in with `--cd-d` stagger (each section: i*80ms unless overridden)
 *   - Default accent #7F77DD with bg rgba(127,119,221,.14) — both override-able
 *
 * Sub-components for stat-grid and bars are exposed as separate components
 * (CpDrillStatGrid + CpDrillBars) for type-safe usage. Or pass raw HTML via `body`
 * for verbatim legacy parity.
 */
import { onBeforeUnmount, onMounted, ref } from "vue";
import { countUpScan } from "@/composables/useCountUp";

export interface CpDrillHero {
  /** Number for the data-countup span */
  value: number | string;
  /** Unit label after the number (e.g. "млрд $") */
  unit?: string;
  /** Big bold caption beneath */
  label?: string;
  /** Smaller grey caption below */
  sub?: string;
  /** Decimals for countup */
  cuDecimals?: number;
}

export interface CpDrillSection {
  title?: string;
  /** Optional count badge after title */
  count?: number;
  /** Body HTML — pass output of CpDrillStatGrid / CpDrillBars / arbitrary HTML */
  body: string;
  /** Override staggered fade-in delay (ms); default i*80 */
  delay?: number;
}

export type CpDrillSize = "sm" | "md" | "lg" | "xl";

const props = withDefaults(
  defineProps<{
    title: string;
    subtitle?: string;
    /** Modal size — sm 480 / md 640 / lg 880 / xl 1100 */
    size?: CpDrillSize;
    /** Accent color (left border + icon bg + section accents) */
    accent?: string;
    /** Accent background (for icon container) */
    accentBg?: string;
    /** Custom icon HTML — defaults to info circle */
    icon?: string;
    /** Hero block (data-driven). Use slot="hero" for full custom. */
    hero?: CpDrillHero | null;
    /** Sections — each renders as title + body */
    sections?: CpDrillSection[];
    /** Footer — small text/HTML or use slot="footer" */
    footer?: string;
  }>(),
  {
    size: "lg",
    accent: "#7F77DD",
    accentBg: "rgba(127,119,221,.14)",
    sections: () => [],
  },
);

const emit = defineEmits<{
  (e: "close"): void;
}>();

const cardRef = ref<HTMLElement | null>(null);
const isClosing = ref(false);

const iconHtml =
  props.icon ||
  `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
     <circle cx="12" cy="12" r="10"/>
     <path d="M12 16v-4M12 8h.01"/>
   </svg>`;

function requestClose() {
  if (isClosing.value) return;
  isClosing.value = true;
  setTimeout(() => {
    emit("close");
  }, 250);
}

function onKeyDown(e: KeyboardEvent) {
  if (e.key === "Escape") requestClose();
}

onMounted(() => {
  document.addEventListener("keydown", onKeyDown);
  // Verbatim legacy timing: setTimeout(_countUpScan(card, 80), 100)
  setTimeout(() => {
    if (cardRef.value) countUpScan(cardRef.value, 80);
  }, 100);
});

onBeforeUnmount(() => {
  document.removeEventListener("keydown", onKeyDown);
});

defineExpose({ requestClose });
</script>

<style scoped>
.cp-drill-bg {
  position: fixed;
  inset: 0;
  background: rgba(15, 18, 40, .55);
  -webkit-backdrop-filter: blur(10px);
  backdrop-filter: blur(10px);
  z-index: var(--z-overlay, 9000);
  display: flex;
  align-items: center;
  justify-content: center;
  animation: cpdBgIn .3s ease;
}

.cp-drill-bg.closing {
  animation: cpdBgOut .25s ease forwards;
}

@keyframes cpdBgIn { from { opacity: 0; } to { opacity: 1; } }
@keyframes cpdBgOut { from { opacity: 1; } to { opacity: 0; } }

.cp-drill-card {
  background: var(--bg1, #fff);
  border: 1px solid var(--card-border, transparent);
  border-radius: 16px;
  max-height: 92dvh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 24px 64px rgba(15, 23, 60, .22), 0 8px 24px rgba(15, 23, 60, .08);
  animation: cpdCardIn .45s var(--ease-standard);
  overflow: hidden;
  position: relative;
}
.cp-drill-card::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0;
  height: 4px; background: var(--cd-accent);
  border-top-left-radius: inherit; border-top-right-radius: inherit;
  animation:
    uzaStripeDrawIn .8s var(--ease-standard) 100ms both,
    uzaStripeBreathe 2.8s ease-in-out 1s infinite;
  pointer-events: none; z-index: 2;
}

.cp-drill-bg.closing .cp-drill-card {
  animation: cpdCardOut .25s cubic-bezier(.4, 0, .6, 1) forwards;
}

@keyframes cpdCardIn {
  from {
    opacity: 0;
    transform: scale(.96) translateY(12px);
  }
  to {
    opacity: 1;
    transform: scale(1) translateY(0);
  }
}

@keyframes cpdCardOut {
  from {
    opacity: 1;
    transform: scale(1) translateY(0);
  }
  to {
    opacity: 0;
    transform: scale(.97) translateY(6px);
  }
}

.cp-drill-card.size-sm { width: min(480px, 96vw); }
.cp-drill-card.size-md { width: min(640px, 96vw); }
.cp-drill-card.size-lg { width: min(880px, 96vw); }
.cp-drill-card.size-xl { width: min(1100px, 96vw); }

/* ===== Header ===== */

.cp-drill-h {
  padding: 16px 22px 14px;
  display: flex;
  align-items: center;
  gap: 12px;
  border-bottom: 1px solid rgba(15, 23, 60, .06);
}

.cp-drill-icn {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background: var(--cd-bg);
  color: var(--cd-accent);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.cp-drill-h-text { flex: 1; min-width: 0; }

.cp-drill-t {
  font-size: 16px;
  font-weight: 600;
  color: var(--t1, #1e2a4a);
  letter-spacing: -.005em;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.cp-drill-s {
  font-size: 11.5px;
  color: rgba(15, 23, 60, .55);
  margin-top: 2px;
  letter-spacing: .01em;
}

.cp-drill-x {
  background: transparent;
  border: none;
  font-size: 24px;
  color: rgba(15, 23, 60, .45);
  cursor: pointer;
  padding: 0 8px;
  line-height: 1;
  transition: color .15s, transform .15s;
}

.cp-drill-x:hover {
  color: var(--t1, #1e2a4a);
  transform: scale(1.1);
}

/* ===== Body ===== */

.cp-drill-body {
  flex: 1;
  overflow-y: auto;
  padding: 18px 22px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* ===== Hero ===== */

.cp-drill-hero {
  background: linear-gradient(135deg,
    color-mix(in srgb, var(--cd-accent) 6%, #fff) 0%,
    color-mix(in srgb, var(--cd-accent) 2%, #fff) 100%);
  border-radius: 12px;
  padding: 18px 20px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  animation: cpdHeroIn .5s var(--ease-standard) backwards;
  animation-delay: 60ms;
}

@keyframes cpdHeroIn {
  from { opacity: 0; transform: translateY(6px); }
  to { opacity: 1; transform: translateY(0); }
}

.cp-drill-hero-numwrap {
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.cp-drill-hero-num {
  font-size: 36px;
  font-weight: 500;
  color: var(--cd-accent);
  letter-spacing: -.025em;
  font-feature-settings: 'tnum';
  line-height: 1;
}

.cp-drill-hero-unit {
  font-size: 14px;
  font-weight: 500;
  color: rgba(15, 23, 60, .65);
  letter-spacing: -.005em;
}

.cp-drill-hero-meta {
  text-align: right;
  max-width: 60%;
}

.cp-drill-hero-lbl {
  font-size: 13px;
  font-weight: 500;
  color: var(--t1, #1e2a4a);
  margin-bottom: 2px;
  letter-spacing: -.005em;
}

.cp-drill-hero-sub {
  font-size: 11px;
  color: rgba(15, 23, 60, .55);
}

/* ===== Section ===== */

.cp-drill-sec {
  animation: cpdSecIn .4s var(--ease-standard) backwards;
  animation-delay: var(--cd-d, 0ms);
}

@keyframes cpdSecIn {
  from { opacity: 0; transform: translateY(4px); }
  to { opacity: 1; transform: translateY(0); }
}

.cp-drill-sec-h {
  font-size: 10.5px;
  font-weight: 600;
  letter-spacing: .07em;
  text-transform: uppercase;
  color: rgba(15, 23, 60, .55);
  margin-bottom: 10px;
  display: flex;
  align-items: center;
  gap: 6px;
}

.cp-drill-sec-cnt {
  color: rgba(15, 23, 60, .35);
  font-weight: 500;
  letter-spacing: 0;
}

/* ===== Footer ===== */

.cp-drill-foot {
  padding: 12px 22px 14px;
  border-top: 1px solid rgba(15, 23, 60, .06);
  font-size: 11px;
  color: rgba(15, 23, 60, .55);
  background: var(--bg2, #FAFAFD);
}

/* Global stat-grid + bars styles — applied via ::v-deep so HTML body renders correctly */
:deep(.cp-drill-stat-grid) {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 8px;
}

:deep(.cp-drill-stat) {
  background: var(--bg2, #FAFAFD);
  border-radius: 8px;
  padding: 10px 12px;
  position: relative;
  overflow: hidden;
}
:deep(.cp-drill-stat)::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0;
  height: 3px; background: var(--cd-accent);
  border-top-left-radius: inherit; border-top-right-radius: inherit;
  animation:
    uzaStripeDrawIn .6s var(--ease-standard) 100ms both,
    uzaStripeBreathe 2.8s ease-in-out 1s infinite;
  pointer-events: none;
}

:deep(.cp-drill-stat.clickable) {
  cursor: pointer;
  transition: transform .15s, background .15s;
}

:deep(.cp-drill-stat.clickable:hover) {
  background: rgba(127, 119, 221, .04);
  transform: translateX(2px);
}

:deep(.cp-drill-stat-l) {
  font-size: 9.5px;
  font-weight: 600;
  letter-spacing: .07em;
  text-transform: uppercase;
  color: rgba(15, 23, 60, .55);
}

:deep(.cp-drill-stat-v) {
  font-size: 18px;
  font-weight: 500;
  color: var(--t1, #1e2a4a);
  margin-top: 4px;
  letter-spacing: -.015em;
  font-feature-settings: 'tnum';
}

:deep(.cp-drill-stat-u) {
  font-size: 12px;
  font-weight: 500;
  color: rgba(15, 23, 60, .55);
  margin-left: 4px;
}

:deep(.cp-drill-stat-s) {
  font-size: 10.5px;
  color: rgba(15, 23, 60, .5);
  margin-top: 2px;
}

:deep(.cp-drill-bars) {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

:deep(.cp-drill-bar-row) {
  display: grid;
  grid-template-columns: minmax(120px, 1.4fr) 2fr minmax(60px, .6fr);
  gap: 10px;
  align-items: center;
  padding: 4px 0;
}

:deep(.cp-drill-bar-row[onclick]) {
  cursor: pointer;
}

:deep(.cp-drill-bar-row[onclick]:hover .cp-drill-bar-l) {
  color: #7F77DD;
}

:deep(.cp-drill-bar-l) {
  font-size: 11.5px;
  color: var(--t1, #1e2a4a);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  transition: color .15s;
}

:deep(.cp-drill-bar-track) {
  height: 14px;
  background: rgba(15, 23, 60, .04);
  border-radius: 7px;
  overflow: hidden;
}

:deep(.cp-drill-bar-fill) {
  height: 100%;
  background: var(--c, #7F77DD);
  width: 0;
  border-radius: 7px;
  animation: cpdBarFill .9s var(--ease-standard) forwards;
  transform-origin: left center;
  animation-delay: var(--bd, 0ms);
}

@keyframes cpdBarFill {
  from { width: 0; }
  to { width: var(--w); }
}

:deep(.cp-drill-bar-v) {
  font-size: 11.5px;
  font-weight: 600;
  color: var(--t1, #1e2a4a);
  font-feature-settings: 'tnum';
  text-align: right;
}
</style>
