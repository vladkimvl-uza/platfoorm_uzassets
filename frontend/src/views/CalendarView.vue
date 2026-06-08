<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useRouter } from "vue-router";
import CompanyCalendar from "@/components/Company/CompanyCalendar.vue";
import { calendarApi } from "@/api/calendar";
import { companiesApi } from "@/api/companies";

const router = useRouter();
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

function onOpen(p: { entity_type: string; entity_id: string; company_id: string | null }) {
  if (p.company_id) router.push(`/library/companies/${p.company_id}`);
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
    <div class="gc-head">
      <div class="gc-head-l">
        <div class="gc-eyebrow">UzAssets · Планирование</div>
        <h1 class="gc-title">Календарь дедлайнов</h1>
      </div>
      <div class="gc-head-r">
        <div class="gc-filter">
          <select v-model="selectedCompany" class="gc-select">
            <option :value="null">Все компании</option>
            <option v-for="c in companies" :key="c.id" :value="c.id">{{ c.name }}</option>
          </select>
        </div>
        <button class="gc-ical-btn" @click="openIcal">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
          Подписаться (iCal)
        </button>
      </div>
    </div>

    <CompanyCalendar :company-id="selectedCompany" @open-entity="onOpen" />

    <!-- iCal modal -->
    <Transition name="gc-modal">
      <div v-if="icalOpen" class="gc-overlay" @click.self="icalOpen = false">
        <div class="gc-modal">
          <div class="gc-modal-head">
            <span>Подписка в календаре</span>
            <button class="gc-modal-x" @click="icalOpen = false">×</button>
          </div>
          <p class="gc-modal-text">
            Добавьте эту ссылку как <b>подписку на календарь</b> в Outlook / Google Calendar / Apple Calendar —
            дедлайны будут появляться и обновляться автоматически.
          </p>
          <div class="gc-url-row">
            <input class="gc-url" :value="icalUrl" readonly @focus="($event.target as HTMLInputElement).select()" />
            <button class="gc-copy" @click="copyIcal">{{ copied ? "Скопировано ✓" : "Копировать" }}</button>
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
.gc-page { max-width: 1180px; margin: 0 auto; padding: 26px 24px 60px; position: relative; }
.gc-head { display: flex; align-items: flex-end; justify-content: space-between; gap: 16px; margin-bottom: 20px; flex-wrap: wrap; }
.gc-eyebrow { font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: .08em; color: var(--t3, #94A3B8); }
.gc-title { font-size: 22px; font-weight: 500; letter-spacing: -.02em; color: var(--t1, #1E2A4A); margin: 4px 0 0; }
.gc-head-r { display: flex; align-items: center; gap: 10px; }
.gc-select {
  font-size: 12.5px; color: var(--t1, #1E2A4A); background: #fff;
  border: 1px solid rgba(15,23,60,.10); border-radius: 9px; padding: 8px 12px; cursor: pointer; font-family: inherit;
}
.gc-ical-btn {
  display: inline-flex; align-items: center; gap: 7px;
  font-size: 12.5px; font-weight: 500; color: #fff; background: var(--p-deep, #534AB7);
  border: none; border-radius: 9px; padding: 8px 14px; cursor: pointer; font-family: inherit;
  transition: background .14s, transform .14s;
}
.gc-ical-btn:hover { background: #463E9F; transform: translateY(-1px); }

.gc-overlay { position: fixed; inset: 0; background: rgba(15,18,40,.45); backdrop-filter: blur(8px); z-index: 9000; display: flex; align-items: center; justify-content: center; padding: 16px; }
.gc-modal { width: 100%; max-width: 480px; background: #fff; border-radius: 14px; padding: 20px 22px 22px; box-shadow: 0 24px 64px rgba(15,23,60,.22); }
.gc-modal-head { display: flex; align-items: center; justify-content: space-between; font-size: 15px; font-weight: 600; color: var(--t1, #1E2A4A); margin-bottom: 10px; }
.gc-modal-x { width: 26px; height: 26px; border: none; background: transparent; color: var(--t3, #94A3B8); font-size: 19px; cursor: pointer; border-radius: 7px; }
.gc-modal-x:hover { background: rgba(15,23,60,.06); }
.gc-modal-text { font-size: 13px; line-height: 1.55; color: var(--t2, #475569); margin: 0 0 14px; }
.gc-url-row { display: flex; gap: 8px; }
.gc-url { flex: 1; font-size: 12px; font-family: ui-monospace, Menlo, monospace; color: var(--t1, #1E2A4A); background: var(--bg-soft, #FAFAFC); border: 1px solid var(--border-input, #E5E7EB); border-radius: 8px; padding: 9px 11px; min-width: 0; }
.gc-copy { font-size: 12px; font-weight: 600; color: #fff; background: #1D9E75; border: none; border-radius: 8px; padding: 9px 14px; cursor: pointer; white-space: nowrap; transition: background .14s; }
.gc-copy:hover { background: #178B66; }
.gc-hint { font-size: 11px; color: var(--t3, #94A3B8); margin-top: 11px; line-height: 1.5; }
.gc-modal-enter-active, .gc-modal-leave-active { transition: opacity .22s; }
.gc-modal-enter-active .gc-modal { transition: transform .3s var(--ease-standard, cubic-bezier(.34,1.2,.64,1)); }
.gc-modal-enter-from { opacity: 0; }
.gc-modal-enter-from .gc-modal { transform: translateY(16px) scale(.96); }
.gc-modal-leave-to { opacity: 0; }
</style>
