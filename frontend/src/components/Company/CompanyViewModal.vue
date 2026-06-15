<script setup lang="ts">
/**
 * CompanyViewModal — премиум-модалка профиля компании (по клику на тикер).
 * Монтируется один раз в AppShell; управляется через useCompanyModal.
 *
 * Показывает: лого/тикер, название, сектор, сайт, ключевые цифры (сотрудники,
 * активность) и сотрудников (аватары → карточка). Кнопки перехода в рабочее
 * пространство и к разделу «Сотрудники». Анимации входа.
 */
import { computed } from "vue";
import { useRouter } from "vue-router";
import { useCompanyModal } from "@/composables/useCompanyModal";
import SectorChip from "@/components/UZA/SectorChip.vue";
import UserCardAnchor from "@/components/user/UserCardAnchor.vue";
import { formatRelativeTime } from "@/api/audit";

const { state, close } = useCompanyModal();
const router = useRouter();

const c = computed(() => ({ ...(state.preview || {}), ...(state.data || {}) } as Record<string, any>));
const website = computed(() => {
  const w = c.value.website;
  if (!w) return null;
  const url = /^https?:\/\//i.test(w) ? w : "https://" + w;
  try { return { href: url, host: new URL(url).host.replace(/^www\./, "") }; }
  catch { return { href: url, host: w }; }
});
const lastActive = computed(() => (c.value.last_active ? formatRelativeTime(c.value.last_active) : null));
const shownEmployees = computed(() => state.employees.slice(0, 8));
const overflow = computed(() => Math.max(0, state.employees.length - shownEmployees.value.length));

function goWorkspace() {
  if (!state.code) return;
  close();
  router.push(`/companies/${state.code}/workspace`);
}
function goPeople() {
  if (!state.code) return;
  close();
  router.push({ path: `/companies/${state.code}/workspace`, query: { tab: "people" } });
}
function onKey(e: KeyboardEvent) { if (e.key === "Escape") close(); }
</script>

<template>
  <Teleport to="body">
    <Transition name="cvm">
      <div v-if="state.open" class="cvm-overlay" @click.self="close" @keydown="onKey" tabindex="-1">
        <div class="cvm" role="dialog" aria-modal="true">
          <button class="cvm-x" @click="close" title="Закрыть">×</button>

          <div class="cvm-banner" :style="{ background: `linear-gradient(135deg, ${c.sector_color || '#7C6FF7'}, ${(c.sector_color || '#534AB7')}22)` }"></div>

          <div class="cvm-head">
            <div class="cvm-logo" :style="{ background: (c.sector_color || '#7C6FF7') + '22', color: c.sector_color || '#534AB7' }">
              <img v-if="c.logo_url" :src="c.logo_url" alt="" />
              <span v-else>{{ (c.bloomberg_ticker || c.code || '?').toString().slice(0, 4).toUpperCase() }}</span>
            </div>
            <div class="cvm-id">
              <div class="cvm-name" :title="c.name_full || c.name">{{ c.name || '—' }}</div>
              <div v-if="c.name_full && c.name_full !== c.name" class="cvm-full">{{ c.name_full }}</div>
              <SectorChip v-if="c.sector" class="cvm-sector" :name="c.sector" :color="c.sector_color" size="sm" />
            </div>
          </div>

          <div class="cvm-body">
            <!-- Метрики -->
            <div class="cvm-stats">
              <button class="cvm-stat" @click="goPeople">
                <span class="cvm-stat-v">{{ c.employees_count ?? '—' }}</span>
                <span class="cvm-stat-l">сотрудников</span>
              </button>
              <a v-if="website" class="cvm-stat cvm-stat-site" :href="website.href" target="_blank" rel="noopener noreferrer">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
                <span class="cvm-stat-host">{{ website.host }}</span>
              </a>
              <div class="cvm-stat cvm-stat-act">
                <span class="cvm-stat-v cvm-stat-act-v">{{ lastActive || '—' }}</span>
                <span class="cvm-stat-l">активность</span>
              </div>
            </div>

            <!-- Сотрудники -->
            <div v-if="shownEmployees.length" class="cvm-sec">
              <div class="cvm-sec-t">Сотрудники</div>
              <div class="cvm-emps">
                <UserCardAnchor
                  v-for="e in shownEmployees" :key="e.id" tag="span" :user-id="e.id" :preview="e" class="cvm-emp"
                >
                  <span class="cvm-emp-av" :style="{ background: e.accent }" :title="e.full_name">
                    <img v-if="e.avatar_url" :src="e.avatar_url" alt="" />
                    <span v-else>{{ e.initials }}</span>
                  </span>
                </UserCardAnchor>
                <button v-if="overflow" class="cvm-emp-av cvm-emp-more" @click="goPeople">+{{ overflow }}</button>
              </div>
            </div>

            <div class="cvm-actions">
              <button class="cvm-btn cvm-btn-primary" @click="goWorkspace">
                Открыть карточку
                <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M5 3l5 5-5 5"/></svg>
              </button>
              <button class="cvm-btn cvm-btn-ghost" @click="goPeople">Сотрудники</button>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.cvm-overlay {
  position: fixed; inset: 0; z-index: 9400;
  background: rgba(20, 16, 40, .46); backdrop-filter: blur(4px);
  display: flex; align-items: center; justify-content: center; padding: 20px;
}
.cvm {
  position: relative; width: 420px; max-width: 100%;
  background: var(--bg1, #fff); border-radius: 20px; overflow: hidden;
  box-shadow: 0 30px 70px -15px rgba(30, 20, 70, .5);
  font-family: Geist, system-ui, sans-serif;
}
.cvm-x {
  position: absolute; top: 12px; right: 12px; z-index: 3;
  width: 28px; height: 28px; border-radius: 9px; border: none;
  background: rgba(255, 255, 255, .25); color: #fff; font-size: 17px; cursor: pointer;
  backdrop-filter: blur(4px); transition: background .14s;
}
.cvm-x:hover { background: rgba(255, 255, 255, .45); }

.cvm-banner { height: 72px; }
/* Лого вынесено абсолютом — только оно перекрывает баннер; название целиком ниже. */
.cvm-head { position: relative; padding: 14px 22px 6px; min-height: 46px; }
.cvm-logo {
  position: absolute; top: -38px; left: 22px;
  width: 76px; height: 76px; border-radius: 18px;
  display: flex; align-items: center; justify-content: center;
  font-weight: 700; font-size: 16px; letter-spacing: .02em; overflow: hidden;
  font-family: Geist, "SF Mono", monospace;
  border: 4px solid var(--bg1, #fff); box-shadow: 0 6px 18px -6px rgba(0, 0, 0, .3);
}
.cvm-logo img { width: 100%; height: 100%; object-fit: contain; padding: 6px; box-sizing: border-box; }
.cvm-id { margin-left: 90px; min-width: 0; }
.cvm-name {
  font-size: 18px; font-weight: 600; color: var(--t1, #1A1730);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.cvm-full { font-size: 12px; color: var(--t3, #8B889C); margin-top: 1px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.cvm-sector { margin-top: 7px; }

.cvm-body { padding: 18px 22px 22px; }
.cvm-stats { display: flex; gap: 9px; margin-bottom: 18px; }
.cvm-stat {
  flex: 1; min-width: 0; display: flex; flex-direction: column; align-items: flex-start; gap: 2px;
  padding: 10px 12px; border-radius: 11px; border: 1px solid var(--line, #ECEAF4);
  background: var(--bg2, #FAFAFC); cursor: pointer; text-decoration: none; font-family: inherit;
  transition: background .14s, border-color .14s;
}
.cvm-stat:hover { background: rgba(124,111,247,.06); border-color: rgba(124,111,247,.3); }
.cvm-stat-v { font-size: 19px; font-weight: 600; color: var(--t1, #1A1730); }
.cvm-stat-act { cursor: default; }
.cvm-stat-act:hover { background: var(--bg2, #FAFAFC); border-color: var(--line, #ECEAF4); }
.cvm-stat-act-v { font-size: 13px; }
.cvm-stat-l { font-size: 10px; color: var(--t3, #8B889C); text-transform: uppercase; letter-spacing: .03em; }
.cvm-stat-site { flex-direction: column; align-items: flex-start; color: var(--p-deep, #534AB7); }
.cvm-stat-site svg { width: 16px; height: 16px; }
.cvm-stat-host { font-size: 12px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 100%; }

.cvm-sec { margin-bottom: 18px; }
.cvm-sec-t { font-size: 10.5px; font-weight: 600; text-transform: uppercase; letter-spacing: .06em; color: var(--t3, #94A3B8); margin-bottom: 10px; }
.cvm-emps { display: flex; align-items: center; }
.cvm-emp { margin-right: -8px; transition: transform .14s; }
.cvm-emp:hover { transform: translateY(-3px); z-index: 2; }
.cvm-emp-av {
  width: 36px; height: 36px; border-radius: 10px; display: inline-flex; align-items: center; justify-content: center;
  color: #fff; font-weight: 600; font-size: 12px; overflow: hidden;
  border: 2px solid var(--bg1, #fff); box-shadow: 0 1px 4px rgba(0,0,0,.18);
}
.cvm-emp-av img { width: 100%; height: 100%; object-fit: cover; }
.cvm-emp-more { background: var(--bg2, #EEEDF4); color: var(--t2, #6B6880); cursor: pointer; font-family: inherit; }
.cvm-emp-more:hover { background: rgba(124,111,247,.14); color: var(--p-deep, #534AB7); }

.cvm-actions { display: flex; gap: 10px; }
.cvm-btn {
  display: inline-flex; align-items: center; justify-content: center; gap: 5px;
  padding: 10px 16px; border-radius: 10px; font-size: 13px; font-weight: 600;
  cursor: pointer; font-family: inherit; border: none; transition: all .14s;
}
.cvm-btn svg { width: 12px; height: 12px; }
.cvm-btn-primary { flex: 1; background: var(--p-deep, #534AB7); color: #fff; }
.cvm-btn-primary:hover { background: #43399E; transform: translateY(-1px); }
.cvm-btn-ghost { background: var(--bg2, #F1F0F7); color: var(--t2, #5F5E5A); }
.cvm-btn-ghost:hover { background: #E7E5F1; }

.cvm-enter-active, .cvm-leave-active { transition: opacity .2s ease; }
.cvm-enter-from, .cvm-leave-to { opacity: 0; }
.cvm-enter-active .cvm { animation: cvmPop .32s cubic-bezier(.34, 1.4, .5, 1); }
@keyframes cvmPop {
  0%   { transform: translateY(16px) scale(.94); opacity: 0; }
  100% { transform: none; opacity: 1; }
}
</style>
