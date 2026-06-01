<script setup lang="ts">
/**
 * SidebarCompaniesSection.vue
 * ─────────────────────────────────────────────────────────────────
 * Collapsible "Компании" group for the sidebar.
 *
 * Structure (when expanded):
 *   [building icon] Компании [22] ▾
 *       ▾ ГОРНО-МЕТАЛЛУРГ. (5)
 *           НГМК
 *           Навоийуран       ← active
 *           АГМК
 *           ...
 *       ▸ НЕФТЬ И ГАЗ (4)
 *       ▸ ЭНЕРГЕТИКА (4)
 *       ▸ ТРАНСПОРТ (6)
 *       ▸ ДРУГОЙ (3)
 *
 * Behavior:
 *   • Top-level button toggles the whole tree.
 *   • Each sector is independently collapsible.
 *   • When the user is on /companies/{code}/* — the tree auto-opens
 *     and the relevant sector auto-expands.
 *   • Click on a company → /companies/{code}/workspace
 *
 * Visual style matches existing .sb-item siblings (dark navy theme).
 */

import { ref, computed, onMounted, watch } from "vue";
import { RouterLink, useRoute } from "vue-router";
import { useCompaniesStore } from "@/stores/companies";

const route = useRoute();
const companiesStore = useCompaniesStore();

// ─── Local state ───
const isOpen = ref<boolean>(route.path.startsWith("/companies/"));
const expandedSectors = ref<Record<string, boolean>>({});

// ─── Actions ───
function toggleAll() {
  isOpen.value = !isOpen.value;
}
function toggleSector(code: string) {
  expandedSectors.value[code] = !expandedSectors.value[code];
}

// ─── Active company detection ───
const activeCode = computed<string | null>(() => {
  const c = route.params.code || route.params.id;
  return c ? String(c).toLowerCase() : null;
});

function isActiveCompany(code: string): boolean {
  return activeCode.value === code.toLowerCase();
}

// ─── Auto-expand sector containing the currently active company ───
function autoExpandActive() {
  if (!activeCode.value) return;
  const sectorCode = companiesStore.findSectorCode(activeCode.value);
  if (sectorCode) {
    expandedSectors.value[sectorCode] = true;
    isOpen.value = true;
  }
}

watch(() => activeCode.value, autoExpandActive);
watch(() => companiesStore.loaded, (loaded) => { if (loaded) autoExpandActive(); });

// ─── Lifecycle ───
onMounted(() => {
  companiesStore.ensureLoaded();
});
</script>

<template>
  <!-- ═══ TOP-LEVEL TOGGLE (looks like .sb-item) ═══ -->
  <button
    type="button"
    class="sb-item sb-co-toggle"
    :class="{ 'sb-co-toggle-open': isOpen }"
    @click="toggleAll"
    title="Список компаний по секторам"
  >
    <!-- Building icon -->
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <path d="M9 21V12h6v9" />
      <path d="M3 9h18" />
    </svg>
    <span class="sb-name">Компании</span>
    <span v-if="companiesStore.totalCount > 0" class="sb-co-badge">{{ companiesStore.totalCount }}</span>
    <svg
      class="sb-co-chev-main"
      :class="{ open: isOpen }"
      width="11" height="11" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"
    >
      <polyline points="9 18 15 12 9 6" />
    </svg>
  </button>

  <!-- ═══ TREE (visible when isOpen) ═══ -->
  <div v-if="isOpen" class="sb-co-tree">
    <!-- Loading skeleton -->
    <div v-if="companiesStore.loading && !companiesStore.loaded" class="sb-co-loading">
      <div class="sb-co-skeleton" v-for="i in 3" :key="i"></div>
    </div>

    <!-- Error state -->
    <div v-else-if="companiesStore.error" class="sb-co-error" :title="companiesStore.error">
      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor"
           stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="10" /><path d="M12 8v4M12 16h.01" />
      </svg>
      <span>Ошибка загрузки</span>
    </div>

    <!-- Sectors -->
    <template v-else>
      <div
        v-for="group in companiesStore.bySector"
        :key="group.sector.code"
        class="sb-co-sector"
      >
        <!-- Sector header (collapsible) -->
        <button
          type="button"
          class="sb-co-sec-header"
          :class="{ open: !!expandedSectors[group.sector.code] }"
          @click="toggleSector(group.sector.code)"
          :title="group.sector.name_ru"
        >
          <svg
            class="sb-co-sec-chev"
            :class="{ open: !!expandedSectors[group.sector.code] }"
            width="9" height="9" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"
          >
            <polyline points="9 18 15 12 9 6" />
          </svg>
          <span class="sb-co-sec-dot" :style="`background: ${group.sector.color}`"></span>
          <span class="sb-co-sec-name">{{ group.sector.name_ru }}</span>
          <span class="sb-co-sec-count">{{ group.companies.length }}</span>
        </button>

        <!-- Company list (visible when sector is expanded) -->
        <div v-if="expandedSectors[group.sector.code]" class="sb-co-list">
          <RouterLink
            v-for="co in group.companies"
            :key="co.id"
            :to="`/companies/${co.code}/workspace`"
            class="sb-co-item"
            :class="{ active: isActiveCompany(co.code) }"
            :style="`--sec-color: ${group.sector.color}`"
            :title="co.name_ru"
          >
            <span class="sb-co-name">{{ co.name_short || co.name_ru }}</span>
          </RouterLink>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
/* ═══ Top-level toggle button — match .sb-item visually ═══ */
.sb-co-toggle {
  /* Override <button> defaults to mimic .sb-item */
  background: transparent;
  border: none;
  width: 100%;
  text-align: left;
  cursor: pointer;
  font: inherit;
  color: inherit;
  /* sb-item base styles will apply via the .sb-item class — but we also
     need to ensure proper alignment for our extra elements (badge + chev). */
  display: flex;
  align-items: center;
}
.sb-co-toggle .sb-name { flex: 1; }

.sb-co-badge {
  font-size: 10px;
  font-weight: 500;
  padding: 1px 7px;
  background: rgba(255, 255, 255, 0.10);
  color: rgba(255, 255, 255, 0.70);
  border-radius: 9px;
  letter-spacing: 0.02em;
  font-variant-numeric: tabular-nums;
  margin-left: auto;
  margin-right: 6px;
  transition: all 200ms;
}
.sb-co-toggle:hover .sb-co-badge {
  background: rgba(127, 119, 221, 0.20);
  color: #DDD8FB;
}
.sb-co-toggle-open .sb-co-badge {
  background: rgba(127, 119, 221, 0.20);
  color: #DDD8FB;
}

.sb-co-chev-main {
  color: rgba(255, 255, 255, 0.45);
  transition: transform 200ms var(--ease-standard);
  flex-shrink: 0;
}
.sb-co-chev-main.open { transform: rotate(90deg); color: rgba(255, 255, 255, 0.85); }

/* ═══ Tree container ═══ */
.sb-co-tree {
  margin: 2px 0 6px 0;
  padding: 4px 0;
  animation: sbCoTreeIn 240ms var(--ease-standard) both;
  /* overflow removed — was clipping nested content */
}
@keyframes sbCoTreeIn {
  from { opacity: 0; transform: translateY(-4px); }
  to   { opacity: 1; transform: translateY(0); }
}

/* ═══ Loading / Error states ═══ */
.sb-co-loading {
  padding: 6px 12px 6px 36px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.sb-co-skeleton {
  height: 10px;
  background: linear-gradient(90deg,
    rgba(255, 255, 255, 0.04) 0%,
    rgba(255, 255, 255, 0.10) 50%,
    rgba(255, 255, 255, 0.04) 100%);
  background-size: 200% 100%;
  animation: sbCoShimmer 1.4s ease-in-out infinite;
  border-radius: 4px;
}
.sb-co-skeleton:nth-child(2) { width: 70%; }
.sb-co-skeleton:nth-child(3) { width: 50%; }
@keyframes sbCoShimmer {
  0%   { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

.sb-co-error {
  display: flex; align-items: center; gap: 6px;
  padding: 6px 12px 6px 36px;
  font-size: 11px;
  color: #FCA5A5;
}

/* ═══ Sector header (uppercase, small caps) ═══ */
.sb-co-sector { margin-bottom: 1px; }

.sb-co-sec-header {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  background: transparent;
  border: none;
  cursor: pointer;
  color: rgba(255, 255, 255, 0.55);
  padding: 6px 12px 6px 28px;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  text-align: left;
  font-family: inherit;
  border-radius: 6px;
  transition: all 150ms;
}
.sb-co-sec-header:hover {
  color: rgba(255, 255, 255, 0.92);
  background: rgba(255, 255, 255, 0.03);
}
.sb-co-sec-header.open {
  color: rgba(255, 255, 255, 0.85);
}

.sb-co-sec-chev {
  flex-shrink: 0;
  transition: transform 200ms var(--ease-standard);
  color: rgba(255, 255, 255, 0.40);
}
.sb-co-sec-chev.open {
  transform: rotate(90deg);
  color: rgba(255, 255, 255, 0.75);
}

.sb-co-sec-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
  box-shadow: 0 0 0 1.5px rgba(255, 255, 255, 0.10);
}

.sb-co-sec-name {
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
}

.sb-co-sec-count {
  font-size: 9px;
  font-weight: 500;
  color: rgba(255, 255, 255, 0.40);
  font-variant-numeric: tabular-nums;
  padding: 1px 5px;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.04);
  letter-spacing: 0;
}

/* ═══ Companies list inside sector ═══ */
.sb-co-list {
  display: flex;
  flex-direction: column;
  gap: 1px;
  padding: 2px 0 5px;
  animation: sbCoListIn 200ms var(--ease-standard) both;
}
@keyframes sbCoListIn {
  from { opacity: 0; }
  to   { opacity: 1; }
}

.sb-co-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px 6px 42px;
  text-decoration: none;
  color: rgba(255, 255, 255, 0.72);
  font-size: 12px;
  font-weight: 400;
  border-radius: 6px;
  transition: all 150ms var(--ease-standard);
  position: relative;
  margin: 0 4px;
}
.sb-co-item::before {
  /* Hairline tree connector */
  content: "";
  position: absolute;
  left: 30px;
  top: 50%;
  width: 6px;
  height: 1px;
  background: rgba(255, 255, 255, 0.12);
  transition: all 200ms;
}
.sb-co-item:hover {
  background: rgba(255, 255, 255, 0.05);
  color: rgba(255, 255, 255, 0.95);
}
.sb-co-item:hover::before {
  background: var(--sec-color, rgba(255, 255, 255, 0.30));
  width: 8px;
  left: 28px;
}

/* Active state — accent bar on the left */
.sb-co-item.active {
  background: linear-gradient(90deg,
    rgba(127, 119, 221, 0.18) 0%,
    rgba(127, 119, 221, 0.08) 100%);
  color: #E5E1FE;
  font-weight: 500;
}
.sb-co-item.active::before {
  display: none;
}
.sb-co-item.active::after {
  content: "";
  position: absolute;
  left: 0;
  top: 4px;
  bottom: 4px;
  width: 3px;
  background: var(--sec-color, #B5AEEC);
  border-radius: 0 2px 2px 0;
}

.sb-co-name {
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
}

/* ═══ Reduced motion ═══ */
@media (prefers-reduced-motion: reduce) {
  .sb-co-tree,
  .sb-co-list,
  .sb-co-skeleton,
  .sb-co-chev-main,
  .sb-co-sec-chev,
  .sb-co-item,
  .sb-co-item::before {
    animation: none !important;
    transition: none !important;
  }
}
</style>