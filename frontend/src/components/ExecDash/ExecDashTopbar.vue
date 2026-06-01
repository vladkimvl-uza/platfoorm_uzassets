<script setup lang="ts">
/**
 * ExecDashTopbar — Row 0 Executive Dashboard.
 * Логотип: Иқтисодиёт ва молия вазирлиги (assets/minfin-logo.png).
 * Тёмный navy текст оригинала плохо читается на тёмном топбаре,
 * поэтому оборачиваем в светлый chip — brand-цвета 1:1, контраст ok.
 */
import { inject, computed, ref, onMounted, onBeforeUnmount } from "vue";
import { useExecutiveDashboard } from "@/composables/useExecutiveDashboard";
import minfinLogoUrl from "@/assets/minfin-logo.png";

const exec = useExecutiveDashboard();
const toggleSidebar = inject<() => void>("toggleSidebar", () => {});

const sectorMenuOpen = ref(false);
const yearMenuOpen = ref(false);

const mainTitle = computed(() => exec.data.value?.title_main || "Программа трансформации государственных предприятий");
const subTitle = computed(() => exec.data.value?.title_sub || `FY ${exec.year.value} · REVIEW`);

function isSectorSelected(id: string): boolean {
  if (!exec.selectedSectors.value.length) return false;
  return exec.selectedSectors.value.includes(id);
}

function onClickOutside(e: MouseEvent) {
  if (!(e.target as HTMLElement).closest(".edt-dropdown-wrap")) {
    sectorMenuOpen.value = false;
    yearMenuOpen.value = false;
  }
}
onMounted(() => document.addEventListener("click", onClickOutside));
onBeforeUnmount(() => document.removeEventListener("click", onClickOutside));
</script>

<template>
  <div class="edt-tb">
    <!-- Sidebar toggle -->
    <button class="edt-burger" @click="toggleSidebar()" title="Скрыть сайдбар">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
        <line x1="3" y1="6" x2="21" y2="6"/>
        <line x1="3" y1="12" x2="21" y2="12"/>
        <line x1="3" y1="18" x2="21" y2="18"/>
      </svg>
    </button>

    <!-- Left: МинФин РУз. Composite: только герб из PNG (обрезка через
         object-fit + width-crop) + белый HTML-текст для тёмного фона. -->
    <div class="edt-l">
      <div class="edt-logo-composite">
        <img :src="minfinLogoUrl" alt="" class="edt-logo-emblem" />
        <div class="edt-logo-text">
          <div class="edt-logo-t1">O'ZBEKISTON RESPUBLIKASI</div>
          <div class="edt-logo-t2">IQTISODIYOT VA MOLIYA</div>
          <div class="edt-logo-t3">VAZIRLIGI</div>
        </div>
      </div>
    </div>

    <!-- Center: Hero title -->
    <div class="edt-hero">
      <div class="edt-hero-main">{{ mainTitle }}</div>
      <div class="edt-hero-sub">{{ subTitle }}</div>
    </div>

    <!-- Right: filters -->
    <div class="edt-r">
      <!-- Sector filter -->
      <div class="edt-dropdown-wrap">
        <button class="edt-pill" @click.stop="sectorMenuOpen = !sectorMenuOpen">
          <span>{{ exec.filteredSectorsLabel.value }}</span>
          <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" stroke-width="1.6">
            <path d="M2 4l3 3 3-3" />
          </svg>
        </button>
        <div v-if="sectorMenuOpen" class="edt-dropdown">
          <div
            class="edt-opt"
            :class="{ on: !exec.selectedSectors.value.length }"
            @click="exec.clearSectors(); sectorMenuOpen = false"
          >
            <span class="edt-check">{{ !exec.selectedSectors.value.length ? '✓' : '' }}</span>
            <span>Все секторы</span>
          </div>
          <div class="edt-divider" />
          <div
            v-for="s in (exec.data.value?.available_sectors || [])"
            :key="s.id"
            class="edt-opt"
            :class="{ on: isSectorSelected(s.id) }"
            @click.stop="exec.toggleSector(s.id)"
          >
            <span class="edt-check">{{ isSectorSelected(s.id) ? '✓' : '' }}</span>
            <span class="edt-opt-dot" :style="{ background: s.color }" />
            <span>{{ s.label }}</span>
          </div>
        </div>
      </div>

      <!-- Year selector -->
      <div class="edt-dropdown-wrap">
        <button class="edt-pill edt-pill-amber" @click.stop="yearMenuOpen = !yearMenuOpen">
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
            <line x1="16" y1="2" x2="16" y2="6" />
            <line x1="8" y1="2" x2="8" y2="6" />
            <line x1="3" y1="10" x2="21" y2="10" />
          </svg>
          <span>FY {{ exec.year.value }}</span>
          <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" stroke-width="1.6">
            <path d="M2 4l3 3 3-3" />
          </svg>
        </button>
        <div v-if="yearMenuOpen" class="edt-dropdown edt-dropdown-narrow">
          <div
            v-for="y in (exec.data.value?.available_years || [exec.year.value])"
            :key="y"
            class="edt-opt"
            :class="{ on: exec.year.value === y }"
            @click="exec.setYear(y); yearMenuOpen = false"
          >
            <span class="edt-check">{{ exec.year.value === y ? '✓' : '' }}</span>
            <span>FY {{ y }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Узбекский флаг bottom strip -->
    <div class="edt-flag" />
  </div>
</template>

<style scoped>
.edt-tb {
  position: relative;
  background: linear-gradient(135deg, #0C1230 0%, #1E2A4A 60%, #2D3E6B 100%);
  padding: 12px 22px;
  display: flex;
  align-items: center;
  gap: 14px;
  color: #fff;
  z-index: 50;
  flex-shrink: 0;
}

.edt-l { display: flex; align-items: center; gap: 10px; flex-shrink: 0; }

/* Composite: PNG-герб (обрезанный до квадрата) + белый HTML-текст.
   Так сохраняем оригинальные цвета пламени, а текст ставим белым
   под тёмный navy-gradient топбар. */
.edt-logo-composite {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 38px;
}
.edt-logo-emblem {
  /* PNG ratio ~3.5:1 (2000x570). Эмблема ~22% слева.
     Cropping через object-fit:cover + object-position:left
     показывает только эмблему, текст PNG обрезается шириной. */
  height: 34px;
  width: 34px;
  object-fit: cover;
  object-position: left center;
  display: block;
  filter: drop-shadow(0 2px 4px rgba(0, 0, 0, 0.25));
}
.edt-logo-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  color: #fff;
  font-family: 'Inter', 'SF Pro', 'Helvetica Neue', Arial, sans-serif;
  line-height: 1.05;
}
.edt-logo-t1 {
  font-size: 6.4px;
  font-weight: 500;
  letter-spacing: 0.09em;
  color: rgba(255, 255, 255, 0.72);
  text-transform: uppercase;
}
.edt-logo-t2 {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.005em;
  color: #fff;
}
.edt-logo-t3 {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.005em;
  color: #fff;
}

/* Legacy single-img class kept for fallback */
.edt-logo-img {
  height: 30px;
  width: auto;
  display: block;
  transition: height 0.25s cubic-bezier(0.22, 0.61, 0.36, 1);
}

/* Hero */
.edt-hero {
  flex: 1 1 220px;
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  min-width: 0;
  padding: 0 14px;
  max-width: 620px;
  margin: 0 auto;
}
.edt-hero-main {
  font-size: clamp(11.5px, 1vw, 13.5px);
  font-weight: 600;
  color: #fff;
  line-height: 1.25;
  letter-spacing: 0.01em;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
}
.edt-hero-sub {
  font-size: 9px;
  color: rgba(250, 199, 117, 0.72);
  letter-spacing: 0.12em;
  text-transform: uppercase;
  font-weight: 600;
  font-feature-settings: "tnum";
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
}

/* Right side */
.edt-r { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }

.edt-icon-btn {
  background: rgba(255, 255, 255, 0.08);
  border: none;
  width: 32px; height: 32px;
  border-radius: 8px;
  color: rgba(255, 255, 255, 0.6);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s;
}
.edt-icon-btn:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.15);
  color: #fff;
}
.edt-icon-btn:disabled { opacity: 0.4; cursor: not-allowed; }

.edt-dropdown-wrap { position: relative; }

.edt-pill {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 6px 14px;
  background: rgba(255, 255, 255, 0.10);
  color: #fff;
  border: 1px solid rgba(255, 255, 255, 0.10);
  border-radius: 8px;
  font-size: 11.5px;
  font-weight: 500;
  cursor: pointer;
  font-family: inherit;
  transition: background 0.15s, border-color 0.15s;
  font-feature-settings: "tnum";
}
.edt-pill:hover {
  background: rgba(255, 255, 255, 0.16);
  border-color: rgba(255, 255, 255, 0.18);
}
.edt-pill-amber {
  background: rgba(250, 199, 117, 0.10);
  border-color: rgba(250, 199, 117, 0.25);
  color: #FAC775;
}
.edt-pill-amber:hover {
  background: rgba(250, 199, 117, 0.15);
  border-color: rgba(250, 199, 117, 0.35);
}

.edt-dropdown {
  position: absolute;
  right: 0;
  top: calc(100% + 5px);
  background: var(--bg1, #fff);
  color: var(--t1, #1E2A4A);
  border-radius: 8px;
  box-shadow: 0 10px 32px rgba(15, 23, 60, 0.22);
  min-width: 220px;
  padding: 5px;
  z-index: 100;
  animation: edtDropIn 0.18s cubic-bezier(0.34, 1.2, 0.64, 1) both;
}
.edt-dropdown-narrow { min-width: 130px; }

.edt-opt {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  font-size: 11.5px;
  font-weight: 500;
  border-radius: 5px;
  cursor: pointer;
  transition: background 0.12s;
}
.edt-opt:hover { background: rgba(127, 119, 221, 0.07); color: #7F77DD; }
.edt-opt.on { background: rgba(127, 119, 221, 0.10); color: #5b54b8; font-weight: 600; }

.edt-check {
  display: inline-block;
  width: 10px;
  text-align: center;
  font-size: 10px;
  color: #5b54b8;
}

.edt-opt-dot {
  width: 8px;
  height: 8px;
  border-radius: 2px;
  display: inline-block;
}

.edt-divider {
  height: 1px;
  background: rgba(0, 0, 0, 0.06);
  margin: 4px 6px;
}

.edt-flag {
  position: absolute;
  left: 0; right: 0;
  bottom: -5px;
  height: 5px;
  background: linear-gradient(
    90deg,
    #0099B5 0%, #0099B5 33%,
    #CE1126 33%, #CE1126 33.5%,
    #FFFFFF 33.5%, #FFFFFF 66.5%,
    #CE1126 66.5%, #CE1126 67%,
    #1EB53A 67%, #1EB53A 100%
  );
  pointer-events: none;
  z-index: 5;
  overflow: hidden;
}
.edt-flag::before {
  content: "";
  position: absolute;
  top: 0; bottom: 0;
  left: 0;
  width: 28%;
  background: linear-gradient(
    115deg,
    transparent 38%,
    rgba(255, 255, 255, 0.10) 45%,
    rgba(255, 255, 255, 0.65) 50%,
    rgba(255, 255, 255, 0.10) 55%,
    transparent 62%
  );
  animation: edtFlagSheen 8s ease-in-out infinite;
  pointer-events: none;
  mix-blend-mode: screen;
}
@keyframes edtFlagSheen {
  0%        { transform: translateX(-150%); }
  60%, 100% { transform: translateX(450%);  }
}

@keyframes edtDropIn {
  0%   { opacity: 0; transform: translateY(-6px) scale(0.97); }
  100% { opacity: 1; transform: translateY(0) scale(1); }
}

@media (max-width: 1100px) {
  .edt-hero-sub { display: none; }
  .edt-hero-main { font-size: 11.5px; }
  .edt-logo-img { height: 24px; }
  .edt-logo-composite { height: 30px; gap: 5px; }
  .edt-logo-emblem { height: 27px; width: 27px; }
  .edt-logo-t1 { font-size: 5.7px; }
  .edt-logo-t2 { font-size: 8.5px; }
  .edt-logo-t3 { font-size: 8.5px; }
}

/* Sidebar toggle */
.edt-burger {
  width: 34px;
  height: 34px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, .08);
  border: 1px solid rgba(255, 255, 255, .12);
  border-radius: 8px;
  color: rgba(255, 255, 255, .85);
  cursor: pointer;
  flex-shrink: 0;
  transition: background .15s, border-color .15s, transform .15s;
  padding: 0;
}
.edt-burger:hover {
  background: rgba(255, 255, 255, .14);
  border-color: rgba(255, 255, 255, .22);
  color: #fff;
}
.edt-burger:active { transform: scale(.94); }
</style>
