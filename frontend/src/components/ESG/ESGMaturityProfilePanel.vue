<script setup lang="ts">
/**
 * ESGMaturityProfilePanel — профиль ESG-зрелости ОДНОЙ компании для встраивания
 * в воркспейс (та же матрица зрелости, что в /esg, но срез по компании): EMS-балл,
 * стадии по 6 измерениям, динамика ESG-рейтингов, годовая таблица ESG-отчётов.
 * Данные из общего getMaturityHeatmap → берём строку своей компании (синк с /esg).
 */
import { computed, ref, watch } from "vue";
import { esgApi, type ESGMaturityHeatmap } from "@/api/esg";
import { ratingsApi, type AgencyRatingBrief, type AgencyRatingHistoryItem } from "@/api/ratings";
import ESGReportsTable from "@/components/ESG/ESGReportsTable.vue";
import ESGMaturityMatrix from "@/components/ESG/ESGMaturityMatrix.vue";
import UzaStateBlock from "@/components/UZA/UzaStateBlock.vue";
import { useI18n } from "@/composables/useI18n";
import { getCurrentIntlLocale } from "@/locale/i18n";
import { i18nKey } from "@/locale/keys";
import { formatOutlook } from "@/components/Ratings/ratingsHelpers";
import { formatRatingDate } from "@/utils/ratingDates";

const { t } = useI18n();


const props = defineProps<{
  companyId: string;
  companyCode: string;
  year: number;
  canEdit?: boolean;
}>();

const loading = ref(true);
const error = ref<string | null>(null);
const heatmap = ref<ESGMaturityHeatmap | null>(null);

async function loadMaturity() {
  loading.value = true;
  error.value = null;
  try {
    heatmap.value = await esgApi.getMaturityHeatmap(props.year);
  } catch (e: any) {
    error.value = e?.response?.data?.detail || t('Не удалось загрузить зрелость');
    heatmap.value = null;
  } finally {
    loading.value = false;
  }
}
watch(() => [props.companyId, props.year], loadMaturity, { immediate: true });

// Срез матрицы зрелости по ОДНОЙ компании — та же редактируемая матрица, что в
// /esg (ISO / отчётность / заверение / рейтинг / климат / риски), но одна строка.
const singleHeatmap = computed<ESGMaturityHeatmap | null>(() => {
  const hm = heatmap.value;
  if (!hm) return null;
  const row = (hm.companies || []).find(c => c.company_id === props.companyId);
  return { ...hm, companies: row ? [row] : [] };
});
const hasRow = computed(() => (singleHeatmap.value?.companies.length || 0) > 0);

// ─── Динамика ESG-рейтингов (read-only, как в ESGMaturityProfileModal) ───
const ratings = ref<AgencyRatingBrief[]>([]);
const ratingsLoading = ref(false);
const histOpen = ref<string | null>(null);
const histItems = ref<AgencyRatingHistoryItem[]>([]);
const histLoading = ref(false);
const ACTION_LBL: Record<string, string> = { create: i18nKey("создан"), update: i18nKey("изменён"), delete: i18nKey("удалён"), snapshot: i18nKey("снимок") };

async function loadRatings() {
  histOpen.value = null;
  ratingsLoading.value = true;
  try {
    const data = await ratingsApi.getCompanyRatings(props.companyCode);
    ratings.value = data.esg || [];
  } catch { ratings.value = []; }
  finally { ratingsLoading.value = false; }
}
watch(() => props.companyCode, loadRatings, { immediate: true });

async function toggleHistory(agency: string) {
  if (histOpen.value === agency) { histOpen.value = null; return; }
  histOpen.value = agency;
  histItems.value = [];
  histLoading.value = true;
  try {
    const data = await ratingsApi.getRatingHistory(props.companyCode, agency);
    histItems.value = data.items || [];
  } catch { histItems.value = []; }
  finally { histLoading.value = false; }
}
function histDate(iso: string): string {
  try { return new Date(iso).toLocaleDateString(getCurrentIntlLocale(), { day: "2-digit", month: "short", year: "numeric" }); }
  catch { return iso; }
}
</script>

<template>
  <div class="mpp">
    <UzaStateBlock v-if="loading" state="loading" :text="t('Загрузка ESG-зрелости…')" />
    <UzaStateBlock v-else-if="error" state="error" variant="block" :text="error" retry @retry="loadMaturity" />

    <template v-else>
      <!-- Матрица зрелости (срез по компании) — 1:1 с /esg, редактируемая -->
      <div v-if="hasRow" class="mpp-matrix">
        <div class="cw-section-label">{{ t('Матрица ESG-зрелости') }}</div>
        <div class="mpp-matrix-scroll">
          <ESGMaturityMatrix :heatmap="singleHeatmap" :can-edit="canEdit" @saved="loadMaturity" />
        </div>
      </div>
      <UzaStateBlock v-else state="empty" variant="inline" :text="t('Матрица зрелости за {value0} год не заполнена', { value0: year })" />

      <!-- Динамика рейтингов -->
      <div class="mpp-rh">
        <div class="mpp-rh-head">
          <span class="mpp-rh-title">{{ t('Динамика рейтингов') }}</span>
          <span class="mpp-rh-src">{{ t('ESG-рейтинги агентств · история изменений') }}</span>
        </div>
        <div v-if="ratingsLoading" class="mpp-rh-empty">{{ t('Загрузка…') }}</div>
        <template v-else>
          <div v-if="ratings.length" class="mpp-rh-list">
            <div v-for="r in ratings" :key="r.id" class="mpp-rh-wrap">
              <div class="mpp-rh-item">
                <div class="mpp-rh-l">
                  <span class="mpp-rh-ag">{{ r.agency }}</span>
                  <span class="mpp-rh-val">{{ r.score || r.rating || '—' }}</span>
                  <span v-if="r.outlook" class="mpp-rh-out">{{ formatOutlook(r.outlook) }}</span>
                </div>
                <div class="mpp-rh-r">
                  <span v-if="r.rating_date || r.rating_date_text" class="mpp-rh-date">{{ formatRatingDate(r.rating_date || r.rating_date_text) }}</span>
                  <a v-if="r.report_url" class="mpp-rh-doc" :href="r.report_url" target="_blank" rel="noopener">{{ t('отчёт') }}</a>
                  <button class="mpp-rh-btn" type="button" :class="{ on: histOpen === r.agency }" @click="toggleHistory(r.agency)">{{ t('история') }}</button>
                </div>
              </div>
              <Transition name="mpp-hist">
                <div v-if="histOpen === r.agency" class="mpp-hist">
                  <div v-if="histLoading" class="mpp-hist-empty">{{ t('Загрузка истории…') }}</div>
                  <template v-else>
                    <div v-if="histItems.length" class="mpp-hist-tl">
                      <div v-for="(h, i) in histItems" :key="h.id" class="mpp-hist-row" :style="{ '--d': (i*40)+'ms' }">
                        <span class="mpp-hist-dot" :class="'a-'+h.action"></span>
                        <span class="mpp-hist-val">{{ h.score || h.rating || '—' }}</span>
                        <span v-if="h.outlook" class="mpp-hist-out">{{ formatOutlook(h.outlook) }}</span>
                        <span class="mpp-hist-act" :class="'a-'+h.action">{{ ACTION_LBL[h.action] || h.action }}</span>
                        <span class="mpp-hist-when">{{ histDate(h.created_at) }}</span>
                        <span v-if="h.changed_by_name" class="mpp-hist-who">· {{ h.changed_by_name }}</span>
                      </div>
                    </div>
                    <div v-else class="mpp-hist-empty">{{ t('История пуста — изменения появятся после правок рейтинга') }}</div>
                  </template>
                </div>
              </Transition>
            </div>
          </div>
          <div v-else class="mpp-rh-empty">{{ t('Независимых ESG-рейтингов пока нет') }}</div>
        </template>
      </div>

      <!-- Годовая таблица ESG-отчётов (редактируемая, с 2021) -->
      <ESGReportsTable :company-id="companyId" :can-edit="canEdit" />
    </template>
  </div>
</template>

<style scoped>
.mpp { display: flex; flex-direction: column; gap: 18px; }

.mpp-matrix .cw-section-label,
.mpp-matrix > div:first-child { margin-bottom: 10px; }
.cw-section-label { font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; color: var(--t2, #6B6880); }
/* Матрица широкая (9 колонок) — скроллим внутри своего контейнера. */
.mpp-matrix-scroll { overflow-x: auto; -webkit-overflow-scrolling: touch; }

/* Динамика рейтингов */
.mpp-rh-head { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; flex-wrap: wrap; margin-bottom: 12px; }
.mpp-rh-title { font-size: 13px; font-weight: 600; color: var(--t1, #1E2A4A); }
.mpp-rh-src { font-size: 10.5px; color: var(--t3, #94A3B8); }
.mpp-rh-empty { font-size: 11.5px; color: var(--t3, #94A3B8); padding: 6px 0; }
.mpp-rh-list { display: flex; flex-direction: column; gap: 8px; }
.mpp-rh-wrap { display: flex; flex-direction: column; }
.mpp-rh-item { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 9px 13px; border-radius: 10px; background: var(--bg2, #FAFAFC); border: 1px solid var(--line, #ECEAF5); }
.mpp-rh-l { display: inline-flex; align-items: baseline; gap: 10px; min-width: 0; }
.mpp-rh-ag { font-size: 12.5px; font-weight: 600; color: var(--t1, #1E2A4A); }
.mpp-rh-val { font-size: 12.5px; font-weight: 600; color: #6C5CE7; font-variant-numeric: tabular-nums; }
.mpp-rh-out { font-size: 11px; color: var(--t2, #475569); }
.mpp-rh-r { display: inline-flex; align-items: center; gap: 12px; flex-shrink: 0; }
.mpp-rh-date { font-size: 10.5px; color: var(--t3, #94A3B8); font-variant-numeric: tabular-nums; }
.mpp-rh-doc { font-size: 10.5px; color: #6C5CE7; text-decoration: none; }
.mpp-rh-doc:hover { text-decoration: underline; }
.mpp-rh-btn { font-size: 10.5px; font-weight: 600; color: var(--t3, #94A3B8); background: transparent; border: 1px solid var(--line, #ECEAF5); border-radius: 7px; padding: 3px 9px; cursor: pointer; transition: all .15s ease; }
.mpp-rh-btn:hover, .mpp-rh-btn.on { color: #6C5CE7; border-color: rgba(108,92,231,.4); background: rgba(108,92,231,.06); }
.mpp-hist { overflow: hidden; padding: 4px 13px 8px; }
.mpp-hist-empty { font-size: 11px; color: var(--t3, #94A3B8); padding: 6px 2px; }
.mpp-hist-tl { display: flex; flex-direction: column; gap: 0; border-left: 2px solid var(--line, #ECEAF5); margin-left: 4px; padding-left: 12px; }
.mpp-hist-row { position: relative; display: flex; align-items: baseline; gap: 7px; padding: 5px 0; font-size: 11.5px; animation: mppHistIn .35s ease var(--d, 0ms) both; }
@keyframes mppHistIn { from { opacity: 0; transform: translateX(-4px); } to { opacity: 1; transform: translateX(0); } }
.mpp-hist-dot { position: absolute; left: -19px; top: 9px; width: 9px; height: 9px; border-radius: 50%; background: #94A3B8; box-shadow: 0 0 0 3px #fff; }
.mpp-hist-dot.a-create { background: #1D9E75; }
.mpp-hist-dot.a-update { background: #6C5CE7; }
.mpp-hist-dot.a-delete { background: #E24B4A; }
.mpp-hist-val { font-weight: 600; color: var(--t1, #1E2A4A); font-variant-numeric: tabular-nums; }
.mpp-hist-out { font-size: 10.5px; color: var(--t2, #475569); }
.mpp-hist-act { font-size: 9.5px; font-weight: 600; border-radius: 5px; padding: 1px 6px; background: #F1F5F9; color: #64748B; }
.mpp-hist-act.a-create { background: #DCFCE7; color: #1D9E75; }
.mpp-hist-act.a-update { background: #EDE9FE; color: #6C5CE7; }
.mpp-hist-act.a-delete { background: #FEE2E2; color: #E24B4A; }
.mpp-hist-when { font-size: 10.5px; color: var(--t3, #94A3B8); font-variant-numeric: tabular-nums; }
.mpp-hist-who { font-size: 10.5px; color: var(--t3, #94A3B8); }
.mpp-hist-enter-active, .mpp-hist-leave-active { transition: max-height .28s ease, opacity .2s ease; max-height: 400px; }
.mpp-hist-enter-from, .mpp-hist-leave-to { max-height: 0; opacity: 0; }
</style>
