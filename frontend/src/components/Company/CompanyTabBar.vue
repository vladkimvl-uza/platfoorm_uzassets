<template>
  <nav ref="navRef" class="company-tabbar">
    <!-- Hidden measuring strip — rendered once with all tabs to compute widths -->
    <div ref="measureRef" class="tabbar-measure" aria-hidden="true">
      <template v-for="(item, idx) in measureItems" :key="`m-${idx}`">
        <span v-if="item.type === 'separator'" class="tabbar-sep"></span>
        <span v-else class="tabbar-tab tab-off">
          {{ item.tab.label }}
          <span v-if="indicators[item.tab.id]?.badge !== undefined" class="badge-num">
            {{ indicators[item.tab.id]!.badge }}
          </span>
          <span
            v-if="indicators[item.tab.id]?.alert"
            :class="['alert-dot', `alert-${indicators[item.tab.id]!.alert}`]"
          ></span>
        </span>
      </template>
    </div>

    <!-- Visible strip — only tabs that fit -->
    <template v-for="(item, idx) in renderedItems" :key="item.type === 'tab' ? item.tab.id : `sep-${idx}`">
      <span v-if="item.type === 'separator'" class="tabbar-sep"></span>
      <button
        v-else
        :class="['tabbar-tab', activeTab === item.tab.id ? 'tab-on' : 'tab-off']"
        @click="onTabClick(item.tab.id)"
      >
        {{ item.tab.label }}
        <span v-if="indicators[item.tab.id]?.badge !== undefined" class="badge-num">
          {{ indicators[item.tab.id]!.badge }}
        </span>
        <span
          v-if="indicators[item.tab.id]?.alert"
          :class="['alert-dot', `alert-${indicators[item.tab.id]!.alert}`]"
          :title="indicators[item.tab.id]?.alertTooltip || ''"
        ></span>
      </button>
    </template>

    <button
      v-if="hiddenTabs.length > 0"
      class="tab-overflow"
      title="Ещё разделы"
      @click.stop="showOverflowMenu = !showOverflowMenu"
    >
      ⋯
    </button>

    <div v-if="showOverflowMenu && hiddenTabs.length > 0" class="overflow-menu">
      <button
        v-for="tab in hiddenTabs"
        :key="tab.id"
        :class="['overflow-menu-item', { active: activeTab === tab.id }]"
        @click="onOverflowSelect(tab.id)"
      >
        <span class="overflow-menu-label">{{ tab.label }}</span>
        <span v-if="indicators[tab.id]?.badge !== undefined" class="badge-num">
          {{ indicators[tab.id]!.badge }}
        </span>
        <span
          v-if="indicators[tab.id]?.alert"
          :class="['alert-dot', `alert-${indicators[tab.id]!.alert}`]"
        ></span>
      </button>
    </div>
  </nav>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, nextTick, watch } from 'vue';
import {
  COMPANY_TABS,
  MOCK_INDICATORS,
  type TabId,
  type TabConfig,
  type TabIndicators,
} from './companyNavConfig';

const props = defineProps<{
  activeTab: TabId;
  indicators?: Record<TabId, TabIndicators>;
}>();

const emit = defineEmits<{ change: [tab: TabId] }>();

const indicators = computed<Record<TabId, TabIndicators>>(
  () => props.indicators || MOCK_INDICATORS,
);

const navRef = ref<HTMLElement | null>(null);
const measureRef = ref<HTMLElement | null>(null);
const visibleTabs = ref<TabConfig[]>([...COMPANY_TABS]);
const hiddenTabs = ref<TabConfig[]>([]);
const showOverflowMenu = ref(false);

// Build tabs + separators interleaved (separator between distinct group ids).
function buildItems(tabs: TabConfig[]) {
  const items: ({ type: 'tab'; tab: TabConfig } | { type: 'separator' })[] = [];
  let prevGroupId: string | null = null;
  for (const tab of tabs) {
    if (prevGroupId !== null && tab.groupId !== prevGroupId) {
      items.push({ type: 'separator' });
    }
    items.push({ type: 'tab', tab });
    prevGroupId = tab.groupId;
  }
  return items;
}

// Always renders all tabs once (offscreen) so we can measure their natural widths.
const measureItems = computed(() => buildItems(COMPANY_TABS));
const renderedItems = computed(() => buildItems(visibleTabs.value));

let resizeObserver: ResizeObserver | null = null;

async function recomputeOverflow() {
  await nextTick();
  if (!navRef.value || !measureRef.value) return;

  const containerWidth = navRef.value.clientWidth;
  // Reserve room for the ⋯ button (≈40px) so we never push it offscreen.
  const overflowBudget = 44;

  // Pull measured widths from the hidden strip — children alternate tabs and separators
  // in the same order as `measureItems`.
  const measureChildren = Array.from(measureRef.value.children) as HTMLElement[];
  const items = measureItems.value;

  let totalNoOverflow = 0;
  const widths: number[] = [];
  for (let i = 0; i < items.length; i++) {
    const w = (measureChildren[i]?.offsetWidth ?? 80) + 1; // +1 for the `gap: 1px`
    widths.push(w);
    totalNoOverflow += w;
  }

  // If everything fits without the ⋯ button, no overflow.
  if (totalNoOverflow <= containerWidth) {
    visibleTabs.value = [...COMPANY_TABS];
    hiddenTabs.value = [];
    return;
  }

  // Otherwise, fit as many leading TAB items as we can, reserving room for ⋯.
  const budget = containerWidth - overflowBudget;
  let used = 0;
  const newVisible: TabConfig[] = [];
  let lastWasTabIdx = -1;
  for (let i = 0; i < items.length; i++) {
    if (used + widths[i] > budget) break;
    const it = items[i];
    if (it.type === 'tab') {
      newVisible.push(it.tab);
      lastWasTabIdx = i;
    }
    used += widths[i];
  }
  // Trim trailing orphan separator (if last accepted item happened to be a separator,
  // it would be stripped by buildItems anyway, but be safe).
  void lastWasTabIdx;
  const newHidden = COMPANY_TABS.filter(t => !newVisible.includes(t));
  visibleTabs.value = newVisible;
  hiddenTabs.value = newHidden;
}

function onTabClick(tabId: TabId) {
  emit('change', tabId);
}

function onOverflowSelect(tabId: TabId) {
  showOverflowMenu.value = false;
  emit('change', tabId);
}

function onDocClick(e: MouseEvent) {
  if (!navRef.value?.contains(e.target as Node)) {
    showOverflowMenu.value = false;
  }
}

// If the active tab moves into hidden because of resize, force it back to visible
// so the user always sees their current section highlighted.
watch(
  () => props.activeTab,
  () => {
    if (hiddenTabs.value.some(t => t.id === props.activeTab)) {
      // Re-run overflow so the visible set adjusts (recomputeOverflow places leading
      // tabs first — this is a UX trade-off: keep stable order rather than reordering).
      recomputeOverflow();
    }
  },
);

onMounted(() => {
  recomputeOverflow();
  if (navRef.value && 'ResizeObserver' in window) {
    resizeObserver = new ResizeObserver(() => recomputeOverflow());
    resizeObserver.observe(navRef.value);
  }
  document.addEventListener('click', onDocClick);
});

onBeforeUnmount(() => {
  resizeObserver?.disconnect();
  document.removeEventListener('click', onDocClick);
});
</script>

<style scoped>
.company-tabbar {
  padding: 7px 14px;
  display: flex;
  gap: 1px;
  align-items: center;
  /* Тёмный navy + дышащее aurora-свечение — единый язык с глобальным топбаром. */
  background: linear-gradient(180deg, #0C1230 0%, #111A3E 100%);
  border-bottom: 0.5px solid rgba(255, 255, 255, 0.06);
  overflow: hidden;
  position: relative;
}
.company-tabbar::before {
  content: "";
  position: absolute;
  inset: 0;
  background:
    radial-gradient(70% 170% at 14% 45%, rgba(127, 119, 221, 0.42), transparent 56%),
    radial-gradient(55% 150% at 88% 30%, rgba(55, 138, 221, 0.22), transparent 60%);
  pointer-events: none;
  z-index: 0;
  opacity: 0.8;
}
.company-tabbar > * { position: relative; z-index: 1; }

/* Hidden measuring strip — rendered but never visible. */
.tabbar-measure {
  position: absolute;
  visibility: hidden;
  pointer-events: none;
  top: -9999px;
  left: -9999px;
  display: flex;
  gap: 1px;
  align-items: center;
}

.tabbar-tab {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 7px 13px;
  font-size: 11.5px;
  font-family: inherit;
  border-radius: 8px;
  cursor: pointer;
  flex-shrink: 0;
  white-space: nowrap;
  transition: background 150ms, color 150ms;
}
.tab-on {
  background: linear-gradient(135deg, #8B7FF0 0%, #7F77DD 55%, #6C5CE7 100%);
  border: 0.5px solid rgba(255, 255, 255, 0.18);
  color: #fff;
  font-weight: 500;
  box-shadow: 0 3px 12px rgba(127, 119, 221, 0.40);
}
.tab-off {
  background: transparent;
  border: none;
  color: rgba(255, 255, 255, 0.62);
  font-weight: 500;
}
.tab-off:hover {
  background: rgba(255, 255, 255, 0.08);
  color: #fff;
}

.tabbar-sep {
  width: 1px;
  height: 18px;
  background: rgba(255, 255, 255, 0.14);
  margin: 0 6px;
  flex-shrink: 0;
}

.badge-num {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 16px;
  height: 16px;
  padding: 0 5px;
  background: rgba(255, 255, 255, 0.18);
  color: rgba(255, 255, 255, 0.92);
  border-radius: 8px;
  font-size: 9.5px;
  font-weight: 500;
  font-variant-numeric: tabular-nums;
}

.alert-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}
.alert-critical {
  background: var(--sev-high);
  animation: pulseDot 2s infinite;
}
.alert-warning {
  background: var(--amber);
}

.tab-overflow {
  margin-left: auto;
  padding: 7px 13px;
  font-size: 11.5px;
  color: rgba(255, 255, 255, 0.62);
  background: transparent;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-family: inherit;
  flex-shrink: 0;
  font-weight: 500;
}
.tab-overflow:hover {
  background: rgba(255, 255, 255, 0.08);
  color: #fff;
}

.overflow-menu {
  position: absolute;
  top: calc(100% + 4px);
  right: 14px;
  background: var(--bg1, #fff);
  border: 0.5px solid var(--border-hard);
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(15, 23, 60, .12), 0 2px 6px rgba(15, 23, 60, .04);
  padding: 4px;
  min-width: 200px;
  z-index: 100;
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.overflow-menu-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px 11px;
  font-size: 11.5px;
  background: transparent;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-family: inherit;
  color: var(--t1, #1E2A4A);
  text-align: left;
  font-weight: 500;
}
.overflow-menu-label { flex: 1; }
.overflow-menu-item:hover {
  background: rgba(127, 119, 221, .05);
}
.overflow-menu-item.active {
  background: rgba(127, 119, 221, .10);
  color: var(--p-deep);
}

@keyframes pulseDot {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: .5; transform: scale(1.3); }
}
@media (prefers-reduced-motion: reduce) {
  .alert-critical { animation: none; }
  .tabbar-tab { transition: none; }
}
</style>
