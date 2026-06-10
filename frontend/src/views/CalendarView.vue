<script setup lang="ts">
import { ref, onMounted, computed } from "vue";
import CompanyCalendar from "@/components/Company/CompanyCalendar.vue";
import { calendarApi } from "@/api/calendar";
import { companiesApi } from "@/api/companies";
import { useEntityEditor } from "@/composables/useEntityEditor";

const { openTask, openProject } = useEntityEditor();
const selectedCompany = ref<string | null>(null);
const companies = ref<{ id: string; name: string }[]>([]);

const icalUrl = ref<string>("");
const icalOpen = ref(false);
const copied = ref(false);

onMounted(async () => {
  try {
    const resp = await companiesApi.list({ limit: 500 } as any);
    companies.value = (resp.items || []).map((c: any) => ({ id: c.id, name: c.name_ru || c.name_short || c.code }));
  } catch { /* ignore */ }
});

const selectedName = computed(() =>
  selectedCompany.value ? (companies.value.find((c) => c.id === selectedCompany.value)?.name || "Компания") : "Все компании"
);

function onOpen(p: { entity_type: string; entity_id: string; company_id: string | null }) {
  // Клик по событию → открыть карточку задачи/проекта (глобальная модалка),
  // а не переходить на страницу компании.
  if (p.entity_type === "project") openProject(p.entity_id);
  else openTask(p.entity_id);
}

async function openIcal() {
  icalOpen.value = true; copied.value = false;
  if (!icalUrl.value) {
    try {
      const { path } = await calendarApi.icalToken();
      icalUrl.value = window.location.origin + path;
    } catch { icalUrl.value = ""; }
  }
}
async function copyIcal() {
  try { await navigator.clipboard.writeText(icalUrl.value); copied.value = true; setTimeout(() => (copied.value = false), 2000); } catch { /* ignore */ }
}
</script>

<template>
  <div class="gc-page">
    <!-- Hero header -->
    <div class="gc-head">
      <div class="gc-head-l">
        <div class="gc-eyebrow">UzAssets · Планирование</div>
        <h1 class="gc-title">Календарь дедлайнов</h1>
        <div class="gc-sub">Сроки проектов и задач по всему портфелю — синхронно с платформой</div>
      </div>
      <div class="gc-head-r">
        <div class="gc-filter">
          <svg class="gc-filter-ic" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7h18M6 12h12M10 17h4"/></svg>
          <select v-model="selectedCompany" class="gc-select" :title="selectedName">
            <option :value="null">Все компании</option>
            <option v-for="c in companies" :key="c.id" :value="c.id">{{ c.name }}</option>
          </select>
          <svg class="gc-filter-chev" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
        </div>
        <button class="gc-ical-btn" @click="openIcal">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
          Подписаться
        </button>
      </div>
    </div>

    <!-- Calendar surface -->
    <div class="gc-surface">
      <CompanyCalendar :company-id="selectedCompany" @open-entity="onOpen" />
    </div>

    <!-- iCal modal -->
    <Transition name="gc-modal">
      <div v-if="icalOpen" class="gc-overlay" @click.self="icalOpen = false">
        <div class="gc-modal">
          <div class="gc-modal-head">
            <div class="gc-modal-ic">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
            </div>
            <span>Подписка в календаре</span>
            <button class="gc-modal-x" @click="icalOpen = false">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            </button>
          </div>
          <p class="gc-modal-text">
            Добавьте эту ссылку как <b>подписку на календарь</b> в Outlook / Google Calendar / Apple Calendar —
            дедлайны будут появляться и обновляться автоматически.
          </p>
          <div class="gc-url-row">
            <input class="gc-url" :value="icalUrl" readonly @focus="($event.target as HTMLInputElement).select()" />
            <button class="gc-copy" :class="{ done: copied }" @click="copyIcal">
              <svg v-if="copied" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
              {{ copied ? "Скопировано" : "Копировать" }}
            </button>
          </div>
          <div class="gc-hint">
            Google: «Другие календари → Добавить по URL». Outlook: «Добавить календарь → Подписаться из интернета».
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.gc-page { max-width: 1180px; margin: 0 auto; padding: 26px 24px 60px; position: relative; --ease: cubic-bezier(.34, 1.2, .64, 1); }

/* Hero */
.gc-head { display: flex; align-items: flex-end; justify-content: space-between; gap: 16px; margin-bottom: 18px; flex-wrap: wrap; animation: gcFade .5s var(--ease) backwards; }
.gc-eyebrow { font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: .08em; color: var(--t3, #94A3B8); }
.gc-title { font-size: 22px; font-weight: 500; letter-spacing: -.02em; color: var(--t1, #1E2A4A); margin: 4px 0 3px; }
.gc-sub { font-size: 12.5px; color: var(--t3, #94A3B8); }
.gc-head-r { display: flex; align-items: center; gap: 10px; animation: gcFade .5s var(--ease) backwards .08s; }

/* Company filter — custom styled select */
.gc-filter { position: relative; display: inline-flex; align-items: center; }
.gc-filter-ic { position: absolute; left: 11px; color: var(--t3, #94A3B8); pointer-events: none; }
.gc-filter-chev { position: absolute; right: 10px; color: var(--t3, #94A3B8); pointer-events: none; }
.gc-select {
  appearance: none; -webkit-appearance: none;
  font-size: 12.5px; font-weight: 500; color: var(--t1, #1E2A4A); background: #fff;
  border: 1px solid rgba(15,23,60,.10); border-radius: 10px; padding: 9px 30px 9px 32px; cursor: pointer; font-family: inherit;
  max-width: 220px; transition: border-color .16s var(--ease), box-shadow .16s var(--ease);
}
.gc-select:hover { border-color: rgba(127,119,221,.35); }
.gc-select:focus { outline: none; border-color: rgba(127,119,221,.5); box-shadow: 0 0 0 3px rgba(127,119,221,.10); }
.gc-ical-btn {
  display: inline-flex; align-items: center; gap: 7px;
  font-size: 12.5px; font-weight: 500; color: #fff;
  background: linear-gradient(135deg, #534AB7, #7F77DD);
  border: none; border-radius: 10px; padding: 9px 15px; cursor: pointer; font-family: inherit;
  box-shadow: 0 4px 14px rgba(83,74,183,.28);
  transition: transform .16s var(--ease), box-shadow .16s var(--ease), filter .16s;
}
.gc-ical-btn:hover { transform: translateY(-2px); box-shadow: 0 8px 22px rgba(83,74,183,.36); filter: brightness(1.04); }
.gc-ical-btn:active { transform: translateY(0); }

/* Surface card wrapping the calendar */
.gc-surface {
  background: #fff; border: 1px solid rgba(15,23,60,.06); border-radius: 16px;
  padding: 16px 16px 8px; box-shadow: 0 1px 3px rgba(15,23,60,.04), 0 12px 40px rgba(15,23,60,.05);
  animation: gcUp .55s var(--ease) backwards .12s;
}

/* Modal */
.gc-overlay { position: fixed; inset: 0; background: rgba(15,18,40,.45); backdrop-filter: blur(8px); z-index: 9000; display: flex; align-items: center; justify-content: center; padding: 16px; }
.gc-modal { width: 100%; max-width: 480px; background: #fff; border-radius: 14px; padding: 20px 22px 22px; box-shadow: 0 24px 64px rgba(15,23,60,.22); }
.gc-modal-head { display: flex; align-items: center; gap: 10px; font-size: 15px; font-weight: 600; color: var(--t1, #1E2A4A); margin-bottom: 12px; }
.gc-modal-ic { width: 34px; height: 34px; border-radius: 10px; display: flex; align-items: center; justify-content: center; background: rgba(127,119,221,.12); color: var(--p-deep, #534AB7); flex-shrink: 0; }
.gc-modal-head > span { flex: 1; }
.gc-modal-x { width: 28px; height: 28px; border: none; background: transparent; color: var(--t3, #94A3B8); cursor: pointer; border-radius: 8px; display: flex; align-items: center; justify-content: center; transition: background .14s, color .14s; }
.gc-modal-x:hover { background: rgba(15,23,60,.06); color: var(--t1, #1E2A4A); }
.gc-modal-text { font-size: 13px; line-height: 1.55; color: var(--t2, #475569); margin: 0 0 14px; }
.gc-url-row { display: flex; gap: 8px; }
.gc-url { flex: 1; font-size: 12px; font-family: ui-monospace, Menlo, monospace; color: var(--t1, #1E2A4A); background: var(--bg-soft, #FAFAFC); border: 1px solid var(--border-input, #E5E7EB); border-radius: 8px; padding: 9px 11px; min-width: 0; }
.gc-copy { display: inline-flex; align-items: center; gap: 5px; font-size: 12px; font-weight: 600; color: #fff; background: #1D9E75; border: none; border-radius: 8px; padding: 9px 14px; cursor: pointer; white-space: nowrap; transition: background .16s var(--ease), transform .16s var(--ease); }
.gc-copy:hover { background: #178B66; transform: translateY(-1px); }
.gc-copy.done { background: #15805C; }
.gc-hint { font-size: 11px; color: var(--t3, #94A3B8); margin-top: 11px; line-height: 1.5; }
.gc-modal-enter-active, .gc-modal-leave-active { transition: opacity .22s; }
.gc-modal-enter-active .gc-modal { transition: transform .34s var(--ease); }
.gc-modal-leave-active .gc-modal { transition: transform .2s; }
.gc-modal-enter-from { opacity: 0; }
.gc-modal-enter-from .gc-modal { transform: translateY(16px) scale(.96); }
.gc-modal-leave-to { opacity: 0; }
.gc-modal-leave-to .gc-modal { transform: scale(.98); }

@keyframes gcFade { from { opacity: 0; } to { opacity: 1; } }
@keyframes gcUp { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }

@media (max-width: 760px) {
  .gc-head-r { width: 100%; }
  .gc-filter { flex: 1; }
  .gc-select { max-width: none; width: 100%; }
  .gc-surface { padding: 10px 8px 4px; border-radius: 14px; }
}
@media (prefers-reduced-motion: reduce) {
  .gc-head, .gc-head-r, .gc-surface { animation: none !important; opacity: 1 !important; transform: none !important; }
}
</style>
