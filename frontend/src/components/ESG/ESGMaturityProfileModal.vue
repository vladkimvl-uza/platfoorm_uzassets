<script setup lang="ts">
/**
 * ESGMaturityProfileModal — профиль ESG-зрелости компании.
 * Radar по 6 измерениям (из heatmap.dim_stage) + разбивка по стадиям.
 * «Динамика рейтингов» — история изменений ESG-рейтингов (read-only).
 * Внизу — годовая таблица ESG-отчётов (ESGReportsTable): редактируемая, с 2021.
 */
import { ref, watch } from "vue";
import ModalShell from "@/components/ModalShell.vue";
import ESGReportsTable from "@/components/ESG/ESGReportsTable.vue";
import type { ESGMaturityCompany } from "@/api/esg";
import { ratingsApi, type AgencyRatingBrief, type AgencyRatingHistoryItem } from "@/api/ratings";
import { useI18n } from "@/composables/useI18n";
const { t } = useI18n();


const props = defineProps<{ company: ESGMaturityCompany | null; canEdit?: boolean }>();
const emit = defineEmits<{ (e: "close"): void }>();

// ─── Динамика (история) ESG-рейтингов — read-only ──────────────────
const ratings = ref<AgencyRatingBrief[]>([]);
const ratingsLoading = ref(false);
const histOpen = ref<string | null>(null);            // agency раскрытой истории
const histItems = ref<AgencyRatingHistoryItem[]>([]);
const histLoading = ref(false);
const ACTION_LBL: Record<string, string> = { create: "создан", update: "изменён", delete: "удалён", snapshot: "снимок" };

async function loadRatings() {
  histOpen.value = null;
  if (!props.company) { ratings.value = []; return; }
  ratingsLoading.value = true;
  try {
    const data = await ratingsApi.getCompanyRatings(props.company.company_code);
    ratings.value = data.esg || [];
  } catch { ratings.value = []; }
  finally { ratingsLoading.value = false; }
}
async function toggleHistory(agency: string) {
  if (histOpen.value === agency) { histOpen.value = null; return; }
  histOpen.value = agency;
  histItems.value = [];
  if (!props.company) return;
  histLoading.value = true;
  try {
    const data = await ratingsApi.getRatingHistory(props.company.company_code, agency);
    histItems.value = data.items || [];
  } catch { histItems.value = []; }
  finally { histLoading.value = false; }
}
function histDate(iso: string): string {
  try { return new Date(iso).toLocaleDateString("ru", { day: "2-digit", month: "short", year: "numeric" }); }
  catch { return iso; }
}

watch(() => props.company, (c) => {
  if (c) loadRatings();
  else ratings.value = [];
}, { immediate: true });
</script>

<template>
  <ModalShell :open="!!company" size="lg" @close="emit('close')">
    <template #header v-if="company">
      <div class="mp-head">
        <div>
          <div class="mp-eyebrow">{{ company.sector_name || company.company_code }} {{ t('· ESG-зрелость') }}</div>
          <div class="mp-title">{{ company.company_name || company.company_code }}</div>
        </div>
      </div>
    </template>

    <!-- Динамика (история) ESG-рейтингов — read-only -->
    <div v-if="company" class="mp-rh">
      <div class="mp-rh-head">
        <span class="mp-rh-title">{{ t('Динамика рейтингов') }}</span>
        <span class="mp-rh-src">{{ t('ESG-рейтинги агентств · история изменений') }}</span>
      </div>
      <div v-if="ratingsLoading" class="mp-rh-empty">{{ t('Загрузка…') }}</div>
      <template v-else>
        <div v-if="ratings.length" class="mp-rh-list">
          <div v-for="r in ratings" :key="r.id" class="mp-rh-wrap">
            <div class="mp-rh-item">
              <div class="mp-rh-l">
                <span class="mp-rh-ag">{{ r.agency }}</span>
                <span class="mp-rh-val">{{ r.score || r.rating || '—' }}</span>
                <span v-if="r.outlook" class="mp-rh-out">{{ r.outlook }}</span>
              </div>
              <div class="mp-rh-r">
                <span v-if="r.rating_date_text" class="mp-rh-date">{{ r.rating_date_text }}</span>
                <a v-if="r.report_url" class="mp-rh-doc" :href="r.report_url" target="_blank" rel="noopener">{{ t('отчёт') }}</a>
                <button class="mp-rh-btn" type="button" :class="{ on: histOpen === r.agency }"
                        @click="toggleHistory(r.agency)">{{ t('история') }}</button>
              </div>
            </div>
            <Transition name="mp-hist">
              <div v-if="histOpen === r.agency" class="mp-hist">
                <div v-if="histLoading" class="mp-hist-empty">{{ t('Загрузка истории…') }}</div>
                <template v-else>
                  <div v-if="histItems.length" class="mp-hist-tl">
                    <div v-for="(h, i) in histItems" :key="h.id" class="mp-hist-row" :style="{ '--d': (i*40)+'ms' }">
                      <span class="mp-hist-dot" :class="'a-'+h.action"></span>
                      <span class="mp-hist-val">{{ h.score || h.rating || '—' }}</span>
                      <span v-if="h.outlook" class="mp-hist-out">{{ h.outlook }}</span>
                      <span class="mp-hist-act" :class="'a-'+h.action">{{ ACTION_LBL[h.action] || h.action }}</span>
                      <span class="mp-hist-when">{{ histDate(h.created_at) }}</span>
                      <span v-if="h.changed_by_name" class="mp-hist-who">· {{ h.changed_by_name }}</span>
                    </div>
                  </div>
                  <div v-else class="mp-hist-empty">{{ t('История пуста — изменения появятся после правок рейтинга') }}</div>
                </template>
              </div>
            </Transition>
          </div>
        </div>
        <div v-else class="mp-rh-empty">{{ t('Независимых ESG-рейтингов пока нет') }}</div>
      </template>
    </div>

    <!-- Годовая таблица ESG-отчётов (редактируемая, с 2021) -->
    <ESGReportsTable v-if="company" :company-id="company.company_id" :can-edit="canEdit" />
  </ModalShell>
</template>

<style scoped>
.mp-head { display: flex; align-items: center; justify-content: space-between; gap: 16px; width: 100%; }
.mp-eyebrow { font-size: 10px; font-weight: 500; letter-spacing: .08em; text-transform: uppercase; color: var(--t3, #94A3B8); }
.mp-title { font-size: 18px; font-weight: 500; color: var(--t1, #1E2A4A); margin-top: 3px; }

/* Динамика рейтингов (история) */
.mp-rh { margin-top: 4px; }
.mp-rh-head { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; flex-wrap: wrap; margin-bottom: 12px; }
.mp-rh-title { font-size: 13px; font-weight: 600; color: var(--t1, #1E2A4A); }
.mp-rh-src { font-size: 10.5px; color: var(--t3, #94A3B8); }
.mp-rh-empty { font-size: 11.5px; color: var(--t3, #94A3B8); padding: 6px 0; }
.mp-rh-list { display: flex; flex-direction: column; gap: 8px; }
.mp-rh-wrap { display: flex; flex-direction: column; }
.mp-rh-item { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 9px 13px; border-radius: 10px; background: var(--surface-2, #FAFAFC); border: 1px solid var(--border, #ECEAF5); }
.mp-rh-l { display: inline-flex; align-items: baseline; gap: 10px; min-width: 0; }
.mp-rh-ag { font-size: 12.5px; font-weight: 600; color: var(--t1, #1E2A4A); }
.mp-rh-val { font-size: 12.5px; font-weight: 600; color: var(--brand, #6C5CE7); font-feature-settings: 'tnum'; }
.mp-rh-out { font-size: 11px; color: var(--t2, #475569); }
.mp-rh-r { display: inline-flex; align-items: center; gap: 12px; flex-shrink: 0; }
.mp-rh-date { font-size: 10.5px; color: var(--t3, #94A3B8); font-feature-settings: 'tnum'; }
.mp-rh-doc { font-size: 10.5px; color: var(--brand, #6C5CE7); text-decoration: none; }
.mp-rh-doc:hover { text-decoration: underline; }
.mp-rh-btn { font-size: 10.5px; font-weight: 600; color: var(--t3, #94A3B8); background: transparent; border: 1px solid var(--border, #ECEAF5); border-radius: 7px; padding: 3px 9px; cursor: pointer; transition: all .15s ease; }
.mp-rh-btn:hover, .mp-rh-btn.on { color: var(--brand, #6C5CE7); border-color: color-mix(in srgb, var(--brand, #6C5CE7) 40%, #fff); background: color-mix(in srgb, var(--brand, #6C5CE7) 6%, #fff); }
.mp-hist { overflow: hidden; padding: 4px 13px 8px; }
.mp-hist-empty { font-size: 11px; color: var(--t3, #94A3B8); padding: 6px 2px; }
.mp-hist-tl { display: flex; flex-direction: column; gap: 0; border-left: 2px solid var(--border, #ECEAF5); margin-left: 4px; padding-left: 12px; }
.mp-hist-row { position: relative; display: flex; align-items: baseline; gap: 7px; padding: 5px 0; font-size: 11.5px; animation: mpHistIn .35s ease var(--d, 0ms) both; }
@keyframes mpHistIn { from { opacity: 0; transform: translateX(-4px); } to { opacity: 1; transform: translateX(0); } }
.mp-hist-dot { position: absolute; left: -19px; top: 9px; width: 9px; height: 9px; border-radius: 50%; background: #94A3B8; box-shadow: 0 0 0 3px #fff; }
.mp-hist-dot.a-create { background: #1D9E75; }
.mp-hist-dot.a-update { background: #6C5CE7; }
.mp-hist-dot.a-delete { background: #E24B4A; }
.mp-hist-val { font-weight: 600; color: var(--t1, #1E2A4A); font-feature-settings: 'tnum'; }
.mp-hist-out { font-size: 10.5px; color: var(--t2, #475569); }
.mp-hist-act { font-size: 9.5px; font-weight: 600; border-radius: 5px; padding: 1px 6px; background: #F1F5F9; color: #64748B; }
.mp-hist-act.a-create { background: #DCFCE7; color: #1D9E75; }
.mp-hist-act.a-update { background: #EDE9FE; color: #6C5CE7; }
.mp-hist-act.a-delete { background: #FEE2E2; color: #E24B4A; }
.mp-hist-when { font-size: 10.5px; color: var(--t3, #94A3B8); font-feature-settings: 'tnum'; }
.mp-hist-who { font-size: 10.5px; color: var(--t3, #94A3B8); }
.mp-hist-enter-active, .mp-hist-leave-active { transition: max-height .28s ease, opacity .2s ease; max-height: 400px; }
.mp-hist-enter-from, .mp-hist-leave-to { max-height: 0; opacity: 0; }

@media (min-width: 2200px) {
  .mp-title { font-size: 24px; }
  .mp-rh-title { font-size: 16px; } .mp-rh-ag, .mp-rh-val { font-size: 15px; }
}
</style>
