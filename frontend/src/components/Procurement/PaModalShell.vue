<script setup lang="ts">
/**
 * PaModalShell — unified modal shell for /procurement-analysis drill modals.
 *
 * Replaces ad-hoc CpDrillModal usage for Phase-2 modals (Company, Supplier,
 * KPI, Purchase, Product). Design pattern matches ConsultantsDrillModal:
 *
 *   ┌────────────────────────────────────────────────┐
 *   │ HEADER (navy gradient + accent border-bottom)  │
 *   │  [kind-pill]  Title here              [×]      │
 *   ├────────────────────────────────────────────────┤
 *   │ STATS STRIP (grid, auto-columns)               │
 *   │  Stat1 │ Stat2 │ Stat3 │ Stat4                 │
 *   ├────────────────────────────────────────────────┤
 *   │ [Tab1] [Tab2] [Tab3]   (optional)              │
 *   ├────────────────────────────────────────────────┤
 *   │ BODY (slot)                                    │
 *   │   Optional aside on the left                   │
 *   │   Main scrollable content                      │
 *   └────────────────────────────────────────────────┘
 *
 * Slots:
 *   #stats — overrides default stats rendering
 *   #tabs  — custom tabs row (or use `tabs` prop with v-model:activeTab)
 *   default — main body content
 *   #aside — optional left side panel
 */
import { ref, onMounted, onBeforeUnmount } from "vue";
import { useI18n } from "@/composables/useI18n";

const { t } = useI18n();

defineProps<{
  kind: string;        // small pill in header ("Компания" / "Поставщик" / etc.)
  title: string;       // big header text
  accent?: string;     // hex color for accent stripe (default purple)
  maxWidth?: string;   // default '1080px'
}>();

const emit = defineEmits<{
  (e: "close"): void;
}>();

const isClosing = ref(false);
function requestClose() {
  if (isClosing.value) return;
  isClosing.value = true;
  setTimeout(() => emit("close"), 220);
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === "Escape") requestClose();
}
onMounted(() => window.addEventListener("keydown", onKeydown));
onBeforeUnmount(() => window.removeEventListener("keydown", onKeydown));
</script>

<template>
  <Teleport to="body">
    <div
      class="pms-backdrop"
      :class="{ 'pms-closing': isClosing }"
      @click.self="requestClose"
    >
      <div
        class="pms-shell"
        :style="{ '--accent': accent || '#7F77DD', maxWidth: maxWidth || '1080px' }"
      >
        <!-- ─── Header ─── -->
        <header class="pms-header">
          <div class="pms-h-l">
            <span class="pms-kind-pill">{{ kind }}</span>
            <h2 class="pms-title">{{ title }}</h2>
          </div>
          <button class="pms-close" @click="requestClose" :aria-label="t('Закрыть')">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M18 6L6 18M6 6l12 12"/>
            </svg>
          </button>
        </header>

        <!-- ─── Stats strip ─── -->
        <section v-if="$slots.stats" class="pms-stats">
          <slot name="stats" />
        </section>

        <!-- ─── Tabs ─── -->
        <nav v-if="$slots.tabs" class="pms-tabs">
          <slot name="tabs" />
        </nav>

        <!-- ─── Body ─── -->
        <div class="pms-body">
          <aside v-if="$slots.aside" class="pms-aside">
            <slot name="aside" />
          </aside>
          <main class="pms-main pms-body-in">
            <slot />
          </main>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.pms-backdrop {
  position: fixed; inset: 0; z-index: 1100;
  background: rgba(13, 16, 36, 0.6);
  -webkit-backdrop-filter: blur(9px) saturate(120%);
  backdrop-filter: blur(9px) saturate(120%);
  display: flex; align-items: flex-start; justify-content: center;
  overflow-y: auto;
  padding: 36px 20px;
  animation: pmsFadeIn 220ms ease;
}
@keyframes pmsFadeIn { from { opacity: 0; } to { opacity: 1; } }

.pms-backdrop.pms-closing { animation: pmsFadeOut 200ms ease forwards; }
@keyframes pmsFadeOut { from { opacity: 1; } to { opacity: 0; } }
.pms-backdrop.pms-closing .pms-shell { animation: pmsShellOut 200ms ease forwards; }
@keyframes pmsShellOut {
  from { opacity: 1; transform: translateY(0) scale(1); }
  to   { opacity: 0; transform: translateY(8px) scale(0.98); }
}

.pms-shell {
  width: 100%;
  background: var(--bg1, #fff);
  border: 1px solid var(--card-border, transparent);
  border-radius: 14px;
  border: 1px solid var(--border1, rgba(0, 0, 0, .08));
  box-shadow: 0 32px 80px rgba(13, 16, 40, .26), 0 10px 28px rgba(13, 16, 40, .12);
  display: flex; flex-direction: column;
  overflow: hidden;
  max-height: calc(100dvh - 72px);
  animation: pmsIn 420ms cubic-bezier(.34, 1.32, .52, 1);
}
@keyframes pmsIn {
  from { opacity: 0; transform: translateY(20px) scale(0.965); }
  to   { opacity: 1; transform: translateY(0) scale(1); }
}
/* премиум: мягкое каскадное проявление статов и таб-строки */
.pms-stats { animation: pmsRise 460ms cubic-bezier(.22,1,.36,1) both; animation-delay: 90ms; }
.pms-tabs  { animation: pmsRise 460ms cubic-bezier(.22,1,.36,1) both; animation-delay: 150ms; }
@keyframes pmsRise { from { opacity: 0; transform: translateY(7px); } to { opacity: 1; transform: none; } }

/* премиум: появление контента тела — мягкий fade-up */
.pms-body-in { animation: pmsBodyIn 420ms cubic-bezier(.22,1,.36,1) both; animation-delay: 180ms; }
@keyframes pmsBodyIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }

@media (prefers-reduced-motion: reduce) {
  .pms-shell, .pms-stats, .pms-tabs, .pms-body-in { animation: none !important; }
  .pms-header::after { animation: none !important; }
}

/* ─── Header ─── */
.pms-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 22px;
  background: linear-gradient(95deg, #1E2A4A 0%, #2D3760 60%, #4B477E 100%);
  color: #fff;
  border-bottom: 3px solid var(--accent, #7F77DD);
  position: relative;
}
/* премиум: деликатный медленный шиммер по accent-border-bottom */
.pms-header::after {
  content: "";
  position: absolute;
  left: 0; right: 0; bottom: -3px;
  height: 3px;
  background: linear-gradient(
    100deg,
    transparent 0%,
    transparent 38%,
    rgba(255, 255, 255, .55) 50%,
    transparent 62%,
    transparent 100%
  );
  background-size: 220% 100%;
  pointer-events: none;
  opacity: .5;
  animation: pmsShimmer 3.2s ease-in-out 1.2s infinite;
}
@keyframes pmsShimmer {
  0%   { background-position: 130% 0; }
  55%  { background-position: -30% 0; }
  100% { background-position: -30% 0; }
}
.pms-h-l { display: flex; flex-direction: column; gap: 4px; min-width: 0; flex: 1; }
.pms-kind-pill {
  font-size: 9.5px; font-weight: 600; letter-spacing: 0.08em;
  text-transform: uppercase;
  padding: 2px 8px;
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.14);
  color: rgba(255, 255, 255, 0.85);
  width: fit-content;
}
.pms-title {
  font-size: 18px; font-weight: 600; color: #fff;
  margin: 0; letter-spacing: -0.01em;
  overflow: hidden; text-overflow: ellipsis;
  white-space: nowrap;
}
.pms-close {
  background: rgba(255, 255, 255, .1);
  border: 1px solid rgba(255, 255, 255, .15);
  color: #fff;
  padding: 6px; border-radius: 7px;
  cursor: pointer;
  transition: background .18s ease, transform .18s cubic-bezier(.22, 1, .36, 1), border-color .18s ease;
  flex-shrink: 0;
  display: inline-flex; align-items: center; justify-content: center;
}
.pms-close:hover {
  background: rgba(255, 255, 255, .22);
  border-color: rgba(255, 255, 255, .3);
  transform: rotate(90deg) scale(1.05);
}
.pms-close:active { transform: rotate(90deg) scale(.95); }
@media (prefers-reduced-motion: reduce) {
  .pms-close { transition: background .18s ease; }
  .pms-close:hover, .pms-close:active { transform: none; }
}

/* ─── Stats strip ─── */
.pms-stats {
  display: grid;
  grid-auto-flow: column;
  grid-auto-columns: minmax(0, 1fr);
  gap: 0;
  padding: 14px 18px;
  border-bottom: 1px solid var(--border1, rgba(0, 0, 0, .06));
  background: var(--bg2, #FAFAFC);
}

/* ─── Tabs ─── */
.pms-tabs {
  display: flex;
  padding: 0 22px;
  border-bottom: 1px solid var(--border1, rgba(0, 0, 0, .06));
  background: var(--bg1, #fff);
  flex-shrink: 0;
}

/* ─── Body ─── */
.pms-body {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  flex: 1; min-height: 0;
  overflow: hidden;
}
.pms-body:has(.pms-aside) {
  grid-template-columns: 280px minmax(0, 1fr);
}

.pms-aside {
  padding: 16px 16px 18px;
  border-right: 1px solid var(--border1, rgba(0, 0, 0, .06));
  background: var(--bg2, #FAFAFC);
  overflow-y: auto;
  display: flex; flex-direction: column; gap: 16px;
}
.pms-main {
  overflow-y: auto;
  display: flex; flex-direction: column;
  min-width: 0;
}

@media (max-width: 860px) {
  .pms-body, .pms-body:has(.pms-aside) { grid-template-columns: 1fr; }
  .pms-aside { border-right: none; border-bottom: 1px solid rgba(0, 0, 0, .06); }
  .pms-stats { grid-auto-flow: row; grid-auto-columns: unset; grid-template-columns: repeat(2, 1fr); }
}
</style>

<!-- ─── Shared utility classes (un-scoped, available to children) ─── -->
<style>
/* ─── Stat cell (used inside #stats slot) ─── */
.pms-stat {
  display: flex; flex-direction: column; gap: 4px;
  padding: 4px 14px;
  border-right: 1px solid rgba(0, 0, 0, .06);
  /* премиум: стаггер снизу-вверх, задержка по позиции */
  animation: pmsStatIn 420ms cubic-bezier(.22, 1, .36, 1) both;
  animation-delay: calc(140ms + var(--i, 0) * 45ms);
}
.pms-stat:nth-child(1) { --i: 0; }
.pms-stat:nth-child(2) { --i: 1; }
.pms-stat:nth-child(3) { --i: 2; }
.pms-stat:nth-child(4) { --i: 3; }
.pms-stat:nth-child(5) { --i: 4; }
.pms-stat:nth-child(6) { --i: 5; }
.pms-stat:nth-child(7) { --i: 6; }
.pms-stat:nth-child(8) { --i: 7; }
.pms-stat:last-child { border-right: none; }
@keyframes pmsStatIn {
  from { opacity: 0; transform: translateY(9px); }
  to   { opacity: 1; transform: none; }
}
/* премиум: мягкое проявление чисел (без count-up) */
.pms-stat-val {
  animation: pmsValIn 520ms cubic-bezier(.22, 1, .36, 1) both;
  animation-delay: calc(230ms + var(--i, 0) * 45ms);
}
@keyframes pmsValIn {
  from { opacity: 0; transform: translateY(3px); filter: blur(2px); }
  to   { opacity: 1; transform: none; filter: blur(0); }
}
@media (prefers-reduced-motion: reduce) {
  .pms-stat, .pms-stat-val { animation: none !important; }
}
.pms-stat-lbl {
  font-size: 9.5px; font-weight: 600; letter-spacing: 0.06em;
  color: var(--t3, var(--t-muted)); text-transform: uppercase;
}
.pms-stat-val {
  font-size: 22px; font-weight: 500;
  color: var(--t1, #1E2A4A);
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.02em;
  line-height: 1.1;
}
.pms-stat-val.pos { color: var(--green); }
.pms-stat-val.neg { color: var(--sev-high); }
.pms-stat-val.warn { color: #D97706; }
.pms-stat-val small {
  font-size: 11px; font-weight: 400;
  color: var(--t3, var(--t-muted));
  margin-left: 2px;
}

/* ─── Tab button (used inside #tabs slot) ─── */
.pms-tab {
  background: transparent;
  border: none;
  padding: 12px 4px;
  margin-right: 24px;
  font-size: 13px; font-weight: 500;
  color: var(--t3, var(--t-muted));
  cursor: pointer;
  position: relative;
  transition: color .2s cubic-bezier(.22, 1, .36, 1);
  display: inline-flex; align-items: center; gap: 8px;
  font-family: inherit;
}
.pms-tab::after {
  content: "";
  position: absolute;
  bottom: -1px; left: 0; right: 0;
  height: 2px;
  background: var(--accent, #7F77DD);
  border-radius: 1px;
  transform: scaleX(0);
  transform-origin: center;
  transition: transform .22s cubic-bezier(.22, 1, .36, 1);
}
.pms-tab:hover { color: var(--t1, #1E2A4A); }
.pms-tab:hover::after { transform: scaleX(.4); opacity: .5; }
.pms-tab.active { color: var(--t1, #1E2A4A); font-weight: 600; }
.pms-tab.active::after { transform: scaleX(1); opacity: 1; }
@media (prefers-reduced-motion: reduce) {
  .pms-tab, .pms-tab::after { transition: none; }
}
.pms-tab-count {
  font-size: 10px; font-weight: 600;
  background: rgba(127, 119, 221, .15);
  color: #5B53C2;
  padding: 1px 7px;
  border-radius: 10px;
  min-width: 18px; text-align: center;
}

/* ─── Section inside aside ─── */
.pms-sec { display: flex; flex-direction: column; gap: 2px; }
.pms-sec-lbl {
  font-size: 10px; font-weight: 600; letter-spacing: 0.06em;
  color: var(--t3, var(--t-muted)); text-transform: uppercase;
  margin-bottom: 4px;
}
.pms-mini-row {
  display: flex; align-items: center; gap: 8px;
  padding: 5px 8px;
  border-radius: 6px;
  font-size: 12px;
  color: var(--t1, #1E2A4A);
  transition: background .12s;
}
.pms-mini-row:hover { background: rgba(127, 119, 221, .06); }
.pms-mini-name {
  flex: 1; min-width: 0;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.pms-mini-num {
  font-size: 11px; font-weight: 600;
  font-variant-numeric: tabular-nums;
  background: rgba(0, 0, 0, .05);
  padding: 1px 7px; border-radius: 8px;
  color: rgba(30, 42, 74, 0.65);
  flex-shrink: 0;
}

/* ─── Generic empty state ─── */
.pms-empty {
  padding: 28px 18px;
  text-align: center; font-style: italic;
  color: var(--t3, var(--t-muted)); font-size: 12px;
}

/* ─── Premium shared motion helpers (available to all child modals) ─── */

/* Стаггер-появление строк таблиц / списков. Применяется на <tr>/строку;
   задержка по индексу через inline-style --i (nth-child fallback ниже). */
@keyframes paIn {
  from { opacity: 0; transform: translateY(7px); }
  to   { opacity: 1; transform: none; }
}
.pa-stagger > tbody > tr,
.pa-stagger-rows > * {
  animation: paIn 380ms cubic-bezier(.22, 1, .36, 1) both;
  animation-delay: calc(var(--i, 0) * 30ms);
}
/* nth-child fallback (capped) для строк без явного --i */
.pa-stagger > tbody > tr:nth-child(1)  { --i: 0; }
.pa-stagger > tbody > tr:nth-child(2)  { --i: 1; }
.pa-stagger > tbody > tr:nth-child(3)  { --i: 2; }
.pa-stagger > tbody > tr:nth-child(4)  { --i: 3; }
.pa-stagger > tbody > tr:nth-child(5)  { --i: 4; }
.pa-stagger > tbody > tr:nth-child(6)  { --i: 5; }
.pa-stagger > tbody > tr:nth-child(7)  { --i: 6; }
.pa-stagger > tbody > tr:nth-child(8)  { --i: 7; }
.pa-stagger > tbody > tr:nth-child(9)  { --i: 8; }
.pa-stagger > tbody > tr:nth-child(10) { --i: 9; }
.pa-stagger > tbody > tr:nth-child(n+11) { --i: 10; }

/* Появление контента активной вкладки при переключении табов
   (CSS-driven, привязка к :key смены вкладки в каждой модалке). */
@keyframes paTabIn {
  from { opacity: 0; transform: translateY(6px); }
  to   { opacity: 1; transform: none; }
}
.pa-tab-in { animation: paTabIn 220ms cubic-bezier(.22, 1, .36, 1) both; }

/* Vue <Transition name="pa-tab"> fade/slide для mode=out-in */
.pa-tab-enter-active { transition: opacity .2s ease, transform .2s cubic-bezier(.22, 1, .36, 1); }
.pa-tab-leave-active { transition: opacity .14s ease, transform .14s ease; }
.pa-tab-enter-from { opacity: 0; transform: translateY(6px); }
.pa-tab-leave-to   { opacity: 0; transform: translateY(-4px); }

@media (prefers-reduced-motion: reduce) {
  .pa-stagger > tbody > tr,
  .pa-stagger-rows > *,
  .pa-tab-in { animation: none !important; }
  .pa-tab-enter-active, .pa-tab-leave-active { transition: none !important; }
}
</style>
