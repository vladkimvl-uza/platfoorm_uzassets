<script setup lang="ts">
/**
 * ExecDashTopbar — Row 0 Executive Dashboard.
 * Логотип: Иқтисодиёт ва молия вазирлиги (assets/minfin-logo.png).
 * Тёмный navy текст оригинала плохо читается на тёмном топбаре,
 * поэтому оборачиваем в светлый chip — brand-цвета 1:1, контраст ok.
 */
import { inject, computed, ref, onMounted, onBeforeUnmount } from "vue";
import { useI18n } from "@/composables/useI18n";
import { useExecutiveDashboard } from "@/composables/useExecutiveDashboard";
import { useCompaniesStore } from "@/stores/companies";
import UzaYearStepper from "@/components/UZA/UzaYearStepper.vue";
import minfinLogoUrl from "@/assets/minfin-logo.png";

const { t } = useI18n();
const exec = useExecutiveDashboard();
const companiesStore = useCompaniesStore();
const toggleSidebar = inject<() => void>("toggleSidebar", () => {});
const openMobileSidebar = inject<() => void>("openMobileSidebar", () => {});
function onBurger() {
  if (typeof window !== "undefined" && window.innerWidth <= 1023) openMobileSidebar();
  else toggleSidebar();
}

const sectorMenuOpen = ref(false);
const yearMenuOpen = ref(false);
const companyMenuOpen = ref(false);
const companySearch = ref("");

const filteredCompanyOptions = computed(() => {
  const q = companySearch.value.trim().toLowerCase();
  const list = exec.pickerCompanies.value;
  if (!q) return list;
  return list.filter((c) => c.name.toLowerCase().includes(q) || c.sector_label.toLowerCase().includes(q));
});
function isCompanySelected(id: string): boolean {
  return exec.selectedCompanies.value.includes(id);
}

const hasActiveFilters = computed(() =>
  exec.selectedSectors.value.length > 0 || exec.selectedCompanies.value.length > 0,
);
function resetFilters() {
  exec.clearSectors();
  exec.clearCompanies();
  sectorMenuOpen.value = false;
  companyMenuOpen.value = false;
}

const mainTitle = computed(() => exec.data.value?.title_main || t("Программа трансформации государственных предприятий"));
const subTitle = computed(() => exec.data.value?.title_sub || `FY ${exec.year.value} · REVIEW`);

function isSectorSelected(id: string): boolean {
  if (!exec.selectedSectors.value.length) return false;
  return exec.selectedSectors.value.includes(id);
}

function closeAllMenus() {
  sectorMenuOpen.value = false;
  yearMenuOpen.value = false;
  companyMenuOpen.value = false;
}
function onClickOutside(e: MouseEvent) {
  if (!(e.target as HTMLElement).closest(".edt-dropdown-wrap")) closeAllMenus();
}
// a11y: Escape закрывает открытый фильтр (и возвращает фокус на его триггер).
function onKeydown(e: KeyboardEvent) {
  if (e.key !== "Escape") return;
  const anyOpen = sectorMenuOpen.value || yearMenuOpen.value || companyMenuOpen.value;
  if (!anyOpen) return;
  const trigger = (e.target as HTMLElement)?.closest?.(".edt-dropdown-wrap")?.querySelector<HTMLElement>(".edt-pill");
  closeAllMenus();
  trigger?.focus?.();
}
onMounted(() => {
  document.addEventListener("click", onClickOutside);
  document.addEventListener("keydown", onKeydown);
  void companiesStore.ensureLoaded();  // полный список компаний для пикера
});
onBeforeUnmount(() => {
  document.removeEventListener("click", onClickOutside);
  document.removeEventListener("keydown", onKeydown);
});
</script>

<template>
  <div class="edt-tb">
    <!-- Sidebar toggle -->
    <button class="edt-burger" @click="onBurger()" :title="t('Меню / свернуть сайдбар')">
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
      <!-- Reset filters -->
      <button v-if="hasActiveFilters" class="edt-reset" @click.stop="resetFilters" :title="t('Сбросить все фильтры')">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/></svg>
        <span>{{ t("Сбросить") }}</span>
      </button>

      <!-- Sector filter -->
      <div class="edt-dropdown-wrap">
        <button class="edt-pill" aria-haspopup="listbox" :aria-expanded="sectorMenuOpen" @click.stop="sectorMenuOpen = !sectorMenuOpen">
          <span>{{ exec.filteredSectorsLabel.value }}</span>
          <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" stroke-width="1.6">
            <path d="M2 4l3 3 3-3" />
          </svg>
        </button>
        <div v-if="sectorMenuOpen" class="edt-dropdown" role="listbox" :aria-label="t('Фильтр по секторам')">
          <div
            class="edt-opt"
            role="option"
            tabindex="0"
            :aria-selected="!exec.selectedSectors.value.length"
            :class="{ on: !exec.selectedSectors.value.length }"
            @click="exec.clearSectors(); sectorMenuOpen = false"
            @keydown.enter.prevent="exec.clearSectors(); sectorMenuOpen = false"
            @keydown.space.prevent="exec.clearSectors(); sectorMenuOpen = false"
          >
            <span class="edt-check">{{ !exec.selectedSectors.value.length ? '✓' : '' }}</span>
            <span>{{ t("Все секторы") }}</span>
          </div>
          <div class="edt-divider" />
          <div
            v-for="s in (exec.data.value?.available_sectors || [])"
            :key="s.id"
            class="edt-opt"
            role="option"
            tabindex="0"
            :aria-selected="isSectorSelected(s.id)"
            :class="{ on: isSectorSelected(s.id) }"
            @click.stop="exec.toggleSector(s.id)"
            @keydown.enter.prevent="exec.toggleSector(s.id)"
            @keydown.space.prevent="exec.toggleSector(s.id)"
          >
            <span class="edt-check">{{ isSectorSelected(s.id) ? '✓' : '' }}</span>
            <span class="edt-opt-dot" :style="{ background: s.color }" />
            <span>{{ t(s.label) }}</span>
          </div>
        </div>
      </div>

      <!-- Company picker (single filter + multi-select benchmarking) -->
      <div class="edt-dropdown-wrap">
        <button
          class="edt-pill"
          :class="{ 'edt-pill-active': exec.selectedCompanies.value.length }"
          aria-haspopup="listbox"
          :aria-expanded="companyMenuOpen"
          @click.stop="companyMenuOpen = !companyMenuOpen"
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 21h18M5 21V7l8-4v18M19 21V11l-6-2"/></svg>
          <span>{{ exec.companyFilterLabel.value }}</span>
          <span v-if="exec.selectedCompanies.value.length >= 2" class="edt-bench-badge">⚖</span>
          <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M2 4l3 3 3-3" /></svg>
        </button>
        <div v-if="companyMenuOpen" class="edt-dropdown edt-dropdown-co" @click.stop>
          <div class="edt-co-search">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/></svg>
            <input v-model="companySearch" :placeholder="t('Поиск компании…')" />
          </div>
          <div class="edt-co-hint">
            {{ t("Выберите 1 — фокус, 2+ — сравнение (бенчмарк)") }}
          </div>
          <div class="edt-co-list" role="listbox" aria-multiselectable="true" :aria-label="t('Выбор компаний')">
            <div
              v-for="c in filteredCompanyOptions"
              :key="c.company_id"
              class="edt-opt edt-co-opt"
              role="option"
              tabindex="0"
              :aria-selected="isCompanySelected(c.company_id)"
              :class="{ on: isCompanySelected(c.company_id) }"
              @click="exec.toggleCompany(c.company_id)"
              @keydown.enter.prevent="exec.toggleCompany(c.company_id)"
              @keydown.space.prevent="exec.toggleCompany(c.company_id)"
            >
              <span class="edt-co-box" :class="{ checked: isCompanySelected(c.company_id) }">
                <svg v-if="isCompanySelected(c.company_id)" width="10" height="10" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round"><path d="M3 8l4 4 6-8"/></svg>
              </span>
              <span class="edt-opt-dot" :style="{ background: c.sector_color }" />
              <span class="edt-co-name">{{ c.name }}</span>
              <span class="edt-co-pct">{{ Math.round(c.pct) }}%</span>
            </div>
            <div v-if="!filteredCompanyOptions.length" class="edt-co-empty">{{ t("Ничего не найдено") }}</div>
          </div>
          <div v-if="exec.selectedCompanies.value.length" class="edt-co-foot">
            <span class="edt-co-count">{{ t("Выбрано: {n}", { n: exec.selectedCompanies.value.length }) }}</span>
            <button class="edt-co-clear" @click="exec.clearCompanies()">{{ t("Сбросить") }}</button>
          </div>
        </div>
      </div>

      <!-- Year selector — единый степпер FY (как везде), золотой акцент -->
      <div class="edt-year-gold">
        <UzaYearStepper tone="dark" prefix="FY "
          :years="exec.data.value?.available_years || [exec.year.value]"
          :model-value="exec.year.value"
          @update:model-value="(y) => exec.setYear(y)" />
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
  flex-wrap: wrap;
  row-gap: 10px;
}
/* Планшет/телефон (≤1023): правый кластер пилюль уходит во 2-й ряд целиком —
   как .ft-cluster/.cw-topbar-r, без горизонтального переполнения на 768-834. */
@media (max-width: 1023px) {
  .edt-r { flex: 1 1 100%; justify-content: flex-start; }
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
  font-family: var(--font);
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
  font-size: 9.5px;
  color: rgba(252, 206, 130, 0.95);
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

/* Reset filters */
.edt-reset {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 6px 12px; border-radius: 8px;
  background: rgba(226, 75, 74, 0.12);
  border: 1px solid rgba(226, 75, 74, 0.28);
  color: #FCA5A5; font-size: 11.5px; font-weight: 500; cursor: pointer; font-family: inherit;
  transition: background .15s, border-color .15s, color .15s;
}
.edt-reset:hover { background: rgba(226, 75, 74, 0.2); border-color: rgba(226, 75, 74, 0.45); color: #FECACA; }
.edt-reset svg { flex-shrink: 0; }

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
  background: rgba(127, 119, 221, 0.20);
  border-color: rgba(127, 119, 221, 0.42);
  color: #EBE9FF;
}
.edt-pill-amber:hover {
  background: rgba(127, 119, 221, 0.30);
  border-color: rgba(127, 119, 221, 0.55);
}

/* Год — единый степпер UzaYearStepper с золотым акцентом (министерский дашборд) */
.edt-year-gold :deep(.uza-ys) { background: rgba(250, 199, 117, 0.12); border-color: rgba(250, 199, 117, 0.30); }
.edt-year-gold :deep(.uza-ys-val) { color: #FAC775; }
.edt-year-gold :deep(.uza-ys-arr) { color: rgba(250, 199, 117, 0.75); }
.edt-year-gold :deep(.uza-ys-arr:not(:disabled):hover) { background: rgba(250, 199, 117, 0.22); color: #FDE4B0; }
.edt-year-gold :deep(.uza-ys-l) { color: rgba(250, 199, 117, 0.60); }

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
  animation: edtDropIn 0.18s var(--ease-standard) both;
}
.edt-dropdown-narrow { min-width: 130px; }

/* Company picker */
.edt-pill-active {
  background: rgba(127, 119, 221, 0.22);
  border-color: rgba(139, 127, 240, 0.5);
  color: #fff;
}
.edt-bench-badge { font-size: 11px; line-height: 1; }
.edt-dropdown-co { min-width: 288px; padding: 8px; }
.edt-co-search {
  display: flex; align-items: center; gap: 7px;
  padding: 7px 10px; margin-bottom: 6px;
  background: var(--bg2, #F4F3F9); border-radius: 8px;
  color: var(--t3, #94A3B8);
}
.edt-co-search input {
  flex: 1; border: none; background: transparent; outline: none;
  font-size: 12px; font-family: inherit; color: var(--t1, #1E2A4A);
}
.edt-co-hint { font-size: 10px; color: var(--t3, #94A3B8); padding: 0 4px 6px; line-height: 1.4; }
.edt-co-list { max-height: 300px; overflow-y: auto; display: flex; flex-direction: column; gap: 1px; }
.edt-co-opt { gap: 9px; }
.edt-co-box {
  width: 16px; height: 16px; flex-shrink: 0; border-radius: 5px;
  border: 1.5px solid var(--border-input, #CBD5E1);
  display: inline-flex; align-items: center; justify-content: center; color: #fff;
  transition: background .12s, border-color .12s;
}
.edt-co-box.checked { background: #7F77DD; border-color: #7F77DD; }
.edt-co-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.edt-co-pct { font-size: 10.5px; font-weight: 600; color: var(--t3, #94A3B8); font-variant-numeric: tabular-nums; }
.edt-co-empty { padding: 14px; text-align: center; font-size: 11.5px; color: var(--t3, #94A3B8); }
.edt-co-foot {
  display: flex; align-items: center; justify-content: space-between;
  margin-top: 7px; padding-top: 7px; border-top: 1px solid rgba(0,0,0,.06);
}
.edt-co-count { font-size: 11px; color: var(--t2, #5F5E5A); font-weight: 500; }
.edt-co-clear {
  background: transparent; border: none; color: var(--sev-high, #E24B4A);
  font-size: 11px; font-weight: 600; cursor: pointer; font-family: inherit; padding: 2px 6px; border-radius: 5px;
}
.edt-co-clear:hover { background: rgba(226,75,74,.08); }

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
.edt-opt:focus-visible { outline: none; box-shadow: inset 0 0 0 2px rgba(127, 119, 221, 0.5); background: rgba(127, 119, 221, 0.07); }
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
  /* «Дыхание» ткани — мягкая пульсация яркости всей полосы. */
  animation: edtFlagBreathe 5s ease-in-out infinite;
}
/* Бегущий световой блик (премиум-перелив), цикл каждые ~6с. */
.edt-flag::before {
  content: "";
  position: absolute;
  top: 0; bottom: 0;
  left: 0;
  width: 26%;
  background: linear-gradient(
    115deg,
    transparent 38%,
    rgba(255, 255, 255, 0.12) 45%,
    rgba(255, 255, 255, 0.75) 50%,
    rgba(255, 255, 255, 0.12) 55%,
    transparent 62%
  );
  animation: edtFlagSheen 6s ease-in-out infinite;
  pointer-events: none;
  mix-blend-mode: screen;
}
/* Развевание: непрерывно бегущие мягкие свето-теневые полосы (рябь ткани). */
.edt-flag::after {
  content: "";
  position: absolute;
  inset: 0;
  background: repeating-linear-gradient(
    100deg,
    transparent 0,
    rgba(255, 255, 255, 0.06) 7px,
    transparent 15px,
    rgba(0, 0, 0, 0.07) 23px,
    transparent 31px
  );
  background-size: 62px 100%;
  animation: edtFlagWave 3.4s linear infinite;
  pointer-events: none;
  mix-blend-mode: overlay;
  opacity: 0.7;
}
@keyframes edtFlagSheen {
  0%        { transform: translateX(-150%); }
  45%       { transform: translateX(450%);  }
  100%      { transform: translateX(450%);  }
}
@keyframes edtFlagWave {
  from { background-position: 0 0; }
  to   { background-position: 62px 0; }
}
@keyframes edtFlagBreathe {
  0%, 100% { filter: brightness(1)    saturate(1);   }
  50%      { filter: brightness(1.13) saturate(1.12); }
}
@media (prefers-reduced-motion: reduce) {
  .edt-flag, .edt-flag::before, .edt-flag::after { animation: none; }
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
