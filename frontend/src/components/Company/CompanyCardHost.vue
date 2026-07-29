<script setup lang="ts">
/**
 * CompanyCardHost — единый плавающий поповер-карточка компании (по тикеру).
 * Монтируется ОДИН раз в AppShell. Любой CompanyTicker с :code открывает его.
 *
 * Показывает: лого/тикер, название, сектор, ссылку на сайт, число сотрудников,
 * последнюю активность и кнопку «Открыть профиль» → карточка компании.
 */
import { computed, onBeforeUnmount, onMounted } from "vue";
import { useRouter } from "vue-router";
import { useCompanyCard } from "@/composables/useCompanyCard";
import SectorChip from "@/components/UZA/SectorChip.vue";
import { formatRelativeTime } from "@/api/audit";
import { useI18n } from "@/composables/useI18n";
const { t } = useI18n();


const { state, setOverCard, closeNow } = useCompanyCard();
const router = useRouter();

const CARD_W = 300;

const merged = computed(() => ({ ...(state.preview || {}), ...(state.data || {}) } as Record<string, any>));

const pos = computed(() => {
  const a = state.anchor;
  if (!a) return { display: "none" } as Record<string, string>;
  const vw = window.innerWidth, vh = window.innerHeight, margin = 10;
  let left = a.left;
  if (left + CARD_W + margin > vw) left = vw - CARD_W - margin;
  if (left < margin) left = margin;
  const spaceBelow = vh - a.bottom;
  const flipUp = spaceBelow < 220 && a.top > spaceBelow;
  const style: Record<string, string> = { left: `${Math.round(left)}px`, width: `${CARD_W}px` };
  if (flipUp) style.bottom = `${Math.round(vh - a.top + 8)}px`;
  else style.top = `${Math.round(a.bottom + 8)}px`;
  return style;
});

const websiteHost = computed(() => {
  const w = merged.value.website;
  if (!w) return null;
  const url = /^https?:\/\//i.test(w) ? w : "https://" + w;
  try { return { href: url, host: new URL(url).host.replace(/^www\./, "") }; }
  catch { return { href: url, host: w }; }
});

const lastActiveLabel = computed(() =>
  merged.value.last_active ? formatRelativeTime(merged.value.last_active) : null,
);

function openProfile() {
  if (!state.code) return;
  closeNow();
  router.push(`/companies/${state.code}/workspace`);
}

function openEmployees() {
  if (!state.code) return;
  closeNow();
  router.push({ path: `/companies/${state.code}/workspace`, query: { tab: "people" } });
}

function onKey(e: KeyboardEvent) { if (e.key === "Escape" && state.visible) closeNow(); }
function onDocClick() { if (state.visible && state.pinned) closeNow(); }
onMounted(() => {
  window.addEventListener("keydown", onKey);
  window.addEventListener("click", onDocClick, true);
});
onBeforeUnmount(() => {
  window.removeEventListener("keydown", onKey);
  window.removeEventListener("click", onDocClick, true);
});
</script>

<template>
  <Teleport to="body">
    <Transition name="ccard">
      <div
        v-if="state.visible"
        class="ccard"
        :style="pos"
        @mouseenter="setOverCard(true)"
        @mouseleave="setOverCard(false)"
        @click.stop
      >
        <div class="ccard-head">
          <div class="ccard-logo" :style="{ background: (merged.sector_color || '#7C6FF7') + '1f', color: merged.sector_color || '#534AB7' }">
            <img v-if="merged.logo_url" :src="merged.logo_url" alt="" />
            <span v-else>{{ (merged.bloomberg_ticker || merged.code || '?').toString().slice(0, 4).toUpperCase() }}</span>
          </div>
          <div class="ccard-id">
            <div class="ccard-name" :title="merged.name_full || merged.name">{{ merged.name || '—' }}</div>
            <div v-if="merged.name_full && merged.name_full !== merged.name" class="ccard-full">{{ merged.name_full }}</div>
            <SectorChip v-if="merged.sector" class="ccard-sector" :name="merged.sector" :color="merged.sector_color" size="sm" />
          </div>
        </div>

        <div class="ccard-stats">
          <button class="ccard-stat" @click.stop="openEmployees" :title="t('Открыть сотрудников')">
            <span class="ccard-stat-v">{{ merged.employees_count ?? '—' }}</span>
            <span class="ccard-stat-l">{{ t('сотрудников') }}</span>
          </button>
          <a v-if="websiteHost" class="ccard-stat ccard-site" :href="websiteHost.href" target="_blank" rel="noopener noreferrer" @click.stop>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
            <span class="ccard-site-host">{{ websiteHost.host }}</span>
          </a>
        </div>

        <div class="ccard-foot">
          <span class="ccard-active">
            <template v-if="merged.is_active === false">{{ t('● Отключена') }}</template>
            <template v-else-if="lastActiveLabel">{{ t('Активность:') }} {{ t(lastActiveLabel) }}</template>
            <template v-else-if="state.loading">{{ t('загрузка…') }}</template>
            <template v-else>{{ t('нет активности') }}</template>
          </span>
          <button class="ccard-open" @click.stop="openProfile">
            {{ t('Профиль') }}
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M5 3l5 5-5 5"/></svg>
          </button>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.ccard {
  position: fixed; z-index: 9000;
  background: var(--bg1, #fff);
  border: 1px solid var(--line, #E8E6F0);
  border-radius: 14px;
  box-shadow: 0 12px 40px -8px rgba(40, 32, 80, .22), 0 2px 8px rgba(40, 32, 80, .08);
  padding: 14px;
  font-family: Geist, system-ui, sans-serif;
}
.ccard-head { display: flex; gap: 11px; align-items: flex-start; }
.ccard-logo {
  width: 44px; height: 44px; border-radius: 11px; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  font-weight: 700; font-size: 12px; letter-spacing: .02em; overflow: hidden;
  font-family: Geist, "SF Mono", monospace;
}
.ccard-logo img { width: 100%; height: 100%; object-fit: contain; }
.ccard-id { min-width: 0; flex: 1; }
.ccard-name {
  font-size: 14px; font-weight: 600; color: var(--t1, #1A1730);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.ccard-full {
  font-size: 11px; color: var(--t3, #8B889C); margin-top: 1px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.ccard-sector { margin-top: 6px; }

.ccard-stats { display: flex; gap: 8px; margin-top: 12px; }
.ccard-stat {
  flex: 1; min-width: 0;
  display: flex; flex-direction: column; align-items: flex-start; gap: 1px;
  padding: 8px 11px; border-radius: 10px; border: 1px solid var(--line, #ECEAF4);
  background: var(--bg2, #FAFAFC); cursor: pointer; text-decoration: none;
  font-family: inherit; transition: background .14s, border-color .14s;
}
.ccard-stat:hover { background: rgba(124,111,247,.06); border-color: rgba(124,111,247,.32); }
.ccard-stat-v { font-size: 16px; font-weight: 600; color: var(--t1, #1A1730); }
.ccard-stat-l { font-size: 10px; color: var(--t3, #8B889C); text-transform: uppercase; letter-spacing: .03em; }
.ccard-site { flex-direction: row; align-items: center; gap: 7px; color: var(--p-deep, #534AB7); }
.ccard-site svg { width: 15px; height: 15px; flex-shrink: 0; }
.ccard-site-host { font-size: 12px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.ccard-foot {
  margin-top: 12px; padding-top: 10px; border-top: 1px solid var(--line, #EEEDF4);
  display: flex; align-items: center; justify-content: space-between; gap: 10px;
}
.ccard-active { font-size: 11px; color: var(--t3, #8B889C); }
.ccard-open {
  display: inline-flex; align-items: center; gap: 4px;
  background: var(--p-deep, #534AB7); color: #fff; border: none;
  padding: 6px 12px; border-radius: 8px; font-size: 12px; font-weight: 600;
  cursor: pointer; font-family: inherit; transition: background .14s, transform .14s;
}
.ccard-open svg { width: 12px; height: 12px; }
.ccard-open:hover { background: #43399E; transform: translateY(-1px); }

.ccard-enter-active, .ccard-leave-active { transition: opacity .16s ease, transform .16s ease; }
.ccard-enter-from, .ccard-leave-to { opacity: 0; transform: translateY(-4px) scale(.98); }
</style>
